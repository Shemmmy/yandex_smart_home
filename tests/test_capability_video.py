from typing import cast
from unittest.mock import patch

from homeassistant.components import camera
from homeassistant.components.camera import Camera, DynamicStreamSettings

# noinspection PyProtectedMember
from homeassistant.components.stream import OUTPUT_IDLE_TIMEOUT, Stream, StreamOutput, StreamSettings
from homeassistant.config import async_process_ha_core_config
from homeassistant.const import ATTR_SUPPORTED_FEATURES
from homeassistant.core import Context, HomeAssistant, State
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.yandex_smart_home import const
from custom_components.yandex_smart_home.capability_video import VideoStreamCapability
from custom_components.yandex_smart_home.const import DOMAIN
from custom_components.yandex_smart_home.error import SmartHomeError
from custom_components.yandex_smart_home.schema import (
    CapabilityType,
    GetStreamInstanceActionState,
    GetStreamInstanceActionStateValue,
    VideoStreamCapabilityInstance,
)

from . import BASIC_CONFIG, MockConfig
from .test_capability import assert_no_capabilities, get_exact_one_capability

ACTION_STATE = GetStreamInstanceActionState(
    instance=VideoStreamCapabilityInstance.GET_STREAM,
    value=GetStreamInstanceActionStateValue(protocols=["hls"]),
)


class MockStream(Stream):
    def __init__(self, hass: HomeAssistant):
        super().__init__(
            hass,
            "test",
            {},
            StreamSettings(
                ll_hls=True,
                min_segment_duration=0,
                part_target_duration=0,
                hls_advance_part_limit=0,
                hls_part_timeout=0,
            ),
            DynamicStreamSettings(),
        )

    def endpoint_url(self, fmt: str) -> str:
        return "/foo"

    def add_provider(self, fmt: str, timeout: int = OUTPUT_IDLE_TIMEOUT) -> StreamOutput:
        pass

    async def start(self) -> None:
        pass


class MockCamera(Camera):
    def camera_image(self, width: int | None = None, height: int | None = None) -> bytes | None:
        pass

    def turn_off(self) -> None:
        pass

    def turn_on(self) -> None:
        pass

    def enable_motion_detection(self) -> None:
        pass

    def disable_motion_detection(self) -> None:
        pass

    async def async_create_stream(self) -> Stream | None:
        return MockStream(self.hass)


class MockCameraUnsupported(MockCamera):
    async def async_create_stream(self) -> Stream | None:
        return None


async def test_capability_video_stream_supported(hass):
    state = State("camera.test", camera.STATE_IDLE, {ATTR_SUPPORTED_FEATURES: camera.CameraEntityFeature.STREAM})
    cap = cast(
        VideoStreamCapability,
        get_exact_one_capability(
            hass, BASIC_CONFIG, state, CapabilityType.VIDEO_STREAM, VideoStreamCapabilityInstance.GET_STREAM
        ),
    )
    assert cap.parameters.dict() == {"protocols": ["hls"]}
    assert cap.get_value() is None
    assert cap.retrievable is False
    assert cap.reportable is False

    state = State("camera.no_stream", camera.STATE_IDLE)
    assert_no_capabilities(
        hass, BASIC_CONFIG, state, CapabilityType.VIDEO_STREAM, VideoStreamCapabilityInstance.GET_STREAM
    )


async def test_capability_video_stream_request_stream(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={const.CONF_CONNECTION_TYPE: const.CONNECTION_TYPE_DIRECT},
        options={const.CONF_CLOUD_STREAM: False},
    )
    config = MockConfig(entry=entry)
    state = State("camera.test", camera.STATE_IDLE, {ATTR_SUPPORTED_FEATURES: camera.CameraEntityFeature.STREAM})
    cap = VideoStreamCapability(hass, config, state)

    with patch(
        "custom_components.yandex_smart_home.capability_video._get_camera_from_entity_id",
        return_value=MockCamera(),
    ):
        assert isinstance(await cap._async_request_stream(state.entity_id), MockStream)

    with patch(
        "custom_components.yandex_smart_home.capability_video._get_camera_from_entity_id",
        return_value=MockCameraUnsupported(),
    ):
        with pytest.raises(SmartHomeError) as e:
            await cap._async_request_stream(state.entity_id)
        assert e.value.code == const.ERR_NOT_SUPPORTED_IN_CURRENT_MODE
        assert e.value.message == "camera.test does not support play stream service"


async def test_capability_video_stream_direct(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={const.CONF_CONNECTION_TYPE: const.CONNECTION_TYPE_DIRECT},
        options={const.CONF_CLOUD_STREAM: False},
    )
    config = MockConfig(entry=entry)
    state = State("camera.test", camera.STATE_IDLE, {ATTR_SUPPORTED_FEATURES: camera.CameraEntityFeature.STREAM})

    cap = cast(
        VideoStreamCapability,
        get_exact_one_capability(
            hass, config, state, CapabilityType.VIDEO_STREAM, VideoStreamCapabilityInstance.GET_STREAM
        ),
    )
    stream = MockStream(hass)

    with patch(
        "custom_components.yandex_smart_home.capability_video.VideoStreamCapability._async_request_stream",
        return_value=stream,
    ):
        with pytest.raises(SmartHomeError) as e:
            await cap.set_instance_state(Context(), ACTION_STATE)
        assert e.value.code == const.ERR_NOT_SUPPORTED_IN_CURRENT_MODE
        assert (
            e.value.message == "Unable to get Home Assistant external URL. "
            "Have you set external URLs in Configuration -> General?"
        )

    await async_process_ha_core_config(hass, {"external_url": "https://example.com"})

    with patch(
        "custom_components.yandex_smart_home.capability_video.VideoStreamCapability._async_request_stream",
        return_value=stream,
    ):
        assert (await cap.set_instance_state(Context(), ACTION_STATE)).dict() == {
            "protocol": "hls",
            "stream_url": "https://example.com/foo",
        }


@pytest.mark.parametrize("connection_type", [const.CONNECTION_TYPE_DIRECT, const.CONNECTION_TYPE_CLOUD])
async def test_capability_video_stream_cloud(hass_platform, connection_type):
    hass = hass_platform

    entry = MockConfigEntry(
        domain=DOMAIN, data={const.CONF_CONNECTION_TYPE: connection_type}, options={const.CONF_CLOUD_STREAM: True}
    )
    config = MockConfig(entry=entry)
    state = State("camera.test", camera.STATE_IDLE, {ATTR_SUPPORTED_FEATURES: camera.CameraEntityFeature.STREAM})

    cap = cast(
        VideoStreamCapability,
        get_exact_one_capability(
            hass, config, state, CapabilityType.VIDEO_STREAM, VideoStreamCapabilityInstance.GET_STREAM
        ),
    )
    stream = MockStream(hass)

    with patch(
        "custom_components.yandex_smart_home.capability_video.VideoStreamCapability._async_request_stream",
        return_value=stream,
    ), patch("custom_components.yandex_smart_home.cloud_stream.CloudStream.start") as mock_start_cloud_stream:
        with pytest.raises(SmartHomeError) as e:
            await cap.set_instance_state(Context(), ACTION_STATE)
        assert e.value.code == const.ERR_NOT_SUPPORTED_IN_CURRENT_MODE
        assert e.value.message == "Failed to start stream"
        mock_start_cloud_stream.assert_called_once()

        assert len(hass.data[DOMAIN][const.CLOUD_STREAMS]) == 1
        cloud_stream = hass.data[DOMAIN][const.CLOUD_STREAMS][state.entity_id]
        cloud_stream._running_stream_id = "foo"
        assert (await cap.set_instance_state(Context(), ACTION_STATE)).dict() == {
            "protocol": "hls",
            "stream_url": "https://stream.yaha-cloud.ru/foo/master_playlist.m3u8",
        }

        assert hass.data[DOMAIN][const.CLOUD_STREAMS][state.entity_id] == cloud_stream
