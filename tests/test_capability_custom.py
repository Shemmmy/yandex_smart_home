from typing import Any, cast

from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_SERVICE,
    CONF_SERVICE_DATA,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Context, State
from homeassistant.helpers.config_validation import dynamic_template
from homeassistant.helpers.template import Template
import pytest
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.yandex_smart_home import const
from custom_components.yandex_smart_home.capability_custom import (
    CustomCapability,
    CustomRangeCapability,
    get_custom_capability,
)
from custom_components.yandex_smart_home.helpers import ActionNotAllowed, APIError
from custom_components.yandex_smart_home.schema import (
    CapabilityType,
    ModeCapabilityInstance,
    ModeCapabilityInstanceActionState,
    ModeCapabilityMode,
    OnOffCapabilityInstance,
    RangeCapabilityInstance,
    RangeCapabilityInstanceActionState,
    ResponseCode,
    ToggleCapabilityInstance,
    ToggleCapabilityInstanceActionState,
)

from . import BASIC_ENTRY_DATA, MockConfigEntryData


class MockCapability(CustomCapability):
    type = CapabilityType.ON_OFF

    @property
    def supported(self) -> bool:
        return True

    @property
    def parameters(self) -> None:
        return None

    def get_value(self) -> Any:
        return self._get_source_value()

    async def set_instance_state(self, *_, **__) -> None:
        pass


async def test_capability_custom(hass):
    cap = MockCapability(hass, BASIC_ENTRY_DATA, {}, OnOffCapabilityInstance.ON, "foo", None)
    assert cap.retrievable is False
    assert cap.reportable is False
    assert cap.get_value() is None

    with pytest.raises(APIError) as e:
        get_custom_capability(
            hass,
            BASIC_ENTRY_DATA,
            {},
            CapabilityType.ON_OFF,
            ToggleCapabilityInstance.IONIZATION,
            "foo",
        )
    assert e.value.message == "Unsupported capability type: devices.capabilities.on_off"


async def test_capability_custom_value(hass):
    hass.states.async_set("switch.state_value", STATE_ON)
    hass.states.async_set("switch.attr_value", STATE_UNKNOWN, {"value": "46"})

    cap = get_custom_capability(
        hass,
        BASIC_ENTRY_DATA,
        {const.CONF_ENTITY_CUSTOM_CAPABILITY_STATE_ENTITY_ID: "switch.state_value"},
        CapabilityType.TOGGLE,
        ToggleCapabilityInstance.IONIZATION,
        "foo",
    )
    assert cap.retrievable is True
    assert cap.get_value() is True
    hass.states.async_set("switch.state_value", STATE_OFF)
    assert cap.get_value() is False

    cap = get_custom_capability(
        hass,
        BASIC_ENTRY_DATA,
        {
            const.CONF_ENTITY_CUSTOM_CAPABILITY_STATE_ENTITY_ID: "switch.attr_value",
            const.CONF_ENTITY_CUSTOM_CAPABILITY_STATE_ATTRIBUTE: "value",
        },
        CapabilityType.RANGE,
        RangeCapabilityInstance.HUMIDITY,
        "foo",
    )
    assert cap.retrievable is True
    assert cap.get_value() == 46.0
    hass.states.async_set("switch.attr_value", STATE_UNKNOWN, {"value": "75"})
    assert cap.get_value() == 75

    cap = get_custom_capability(
        hass, BASIC_ENTRY_DATA, {}, CapabilityType.RANGE, RangeCapabilityInstance.HUMIDITY, "foo"
    )
    assert cap.retrievable is False
    assert cap.get_value() is None

    cap = get_custom_capability(
        hass,
        BASIC_ENTRY_DATA,
        {
            const.CONF_ENTITY_CUSTOM_CAPABILITY_STATE_TEMPLATE: Template("{{ 1 + 2 }}"),
        },
        CapabilityType.RANGE,
        RangeCapabilityInstance.HUMIDITY,
        "foo",
    )
    assert cap.retrievable is True
    assert cap.get_value() == 3

    cap = get_custom_capability(
        hass,
        BASIC_ENTRY_DATA,
        {
            const.CONF_ENTITY_CUSTOM_CAPABILITY_STATE_TEMPLATE: Template("{{ 1/0 }}"),
        },
        CapabilityType.RANGE,
        RangeCapabilityInstance.HUMIDITY,
        "foo",
    )
    assert cap.retrievable is True
    with pytest.raises(APIError) as e:
        cap.get_value()
    assert e.value.code == ResponseCode.INVALID_VALUE
    assert (
        e.value.message == "Failed to get current value for instance humidity of range capability of foo: "
        "TemplateError('ZeroDivisionError: division by zero')"
    )


async def test_capability_custom_mode(hass):
    cap = get_custom_capability(
        hass,
        BASIC_ENTRY_DATA,
        {const.CONF_ENTITY_CUSTOM_MODE_SET_MODE: None},
        CapabilityType.MODE,
        ModeCapabilityInstance.CLEANUP_MODE,
        "foo",
    )
    assert cap.supported is False

    state = State("switch.test", "mode_1", {})
    hass.states.async_set(state.entity_id, state.state)
    entry_data = MockConfigEntryData(
        entity_config={
            state.entity_id: {
                const.CONF_ENTITY_MODE_MAP: {
                    "cleanup_mode": {
                        ModeCapabilityMode.ONE: ["mode_1"],
                        ModeCapabilityMode.TWO: ["mode_2"],
                    }
                }
            }
        }
    )

    cap = get_custom_capability(
        hass,
        entry_data,
        {
            const.CONF_ENTITY_CUSTOM_CAPABILITY_STATE_ENTITY_ID: state.entity_id,
        },
        CapabilityType.MODE,
        ModeCapabilityInstance.CLEANUP_MODE,
        state.entity_id,
    )
    assert cap.supported is True
    assert cap.retrievable is True
    assert cap.reportable is True
    assert cap.get_value() == "one"

    with pytest.raises(ActionNotAllowed):
        await cap.set_instance_state(
            Context(),
            ModeCapabilityInstanceActionState(
                instance=ModeCapabilityInstance.CLEANUP_MODE, value=ModeCapabilityMode.ONE
            ),
        )

    cap = get_custom_capability(
        hass,
        entry_data,
        {
            const.CONF_ENTITY_CUSTOM_MODE_SET_MODE: {
                CONF_SERVICE: "test.set_mode",
                ATTR_ENTITY_ID: "switch.test",
                CONF_SERVICE_DATA: {"service_mode": dynamic_template("mode: {{ mode }}")},
            },
        },
        CapabilityType.MODE,
        ModeCapabilityInstance.CLEANUP_MODE,
        state.entity_id,
    )
    assert cap.supported is True
    assert cap.retrievable is False
    assert cap.reportable is False
    assert cap.get_value() is None

    cap = get_custom_capability(
        hass,
        entry_data,
        {
            const.CONF_ENTITY_CUSTOM_CAPABILITY_STATE_ENTITY_ID: state.entity_id,
            const.CONF_ENTITY_CUSTOM_MODE_SET_MODE: {
                CONF_SERVICE: "test.set_mode",
                ATTR_ENTITY_ID: "switch.test",
                CONF_SERVICE_DATA: {"service_mode": dynamic_template("mode: {{ mode }}")},
            },
        },
        CapabilityType.MODE,
        ModeCapabilityInstance.CLEANUP_MODE,
        state.entity_id,
    )
    assert cap.supported is True
    assert cap.retrievable is True
    assert cap.reportable is True
    assert cap.get_value() == "one"

    calls = async_mock_service(hass, "test", "set_mode")
    await cap.set_instance_state(
        Context(),
        ModeCapabilityInstanceActionState(instance=ModeCapabilityInstance.CLEANUP_MODE, value=ModeCapabilityMode.ONE),
    )
    assert len(calls) == 1
    assert calls[0].data == {"service_mode": "mode: mode_1", ATTR_ENTITY_ID: "switch.test"}

    for t in ("", STATE_UNKNOWN, "None", STATE_UNAVAILABLE):
        assert cap.new_with_value_template(Template(t)).get_value() is None


async def test_capability_custom_toggle(hass):
    cap = get_custom_capability(
        hass,
        BASIC_ENTRY_DATA,
        {const.CONF_ENTITY_CUSTOM_TOGGLE_TURN_ON: None, const.CONF_ENTITY_CUSTOM_TOGGLE_TURN_OFF: None},
        CapabilityType.TOGGLE,
        ToggleCapabilityInstance.IONIZATION,
        "foo",
    )
    assert cap.supported is True
    assert cap.retrievable is False
    assert cap.reportable is False
    assert cap.get_value() is None

    state = State("switch.test", STATE_ON, {})
    hass.states.async_set(state.entity_id, state.state)
    cap = get_custom_capability(
        hass,
        BASIC_ENTRY_DATA,
        {const.CONF_ENTITY_CUSTOM_CAPABILITY_STATE_ENTITY_ID: state.entity_id},
        CapabilityType.TOGGLE,
        ToggleCapabilityInstance.IONIZATION,
        "foo",
    )
    assert cap.supported is True
    assert cap.retrievable is True
    assert cap.reportable is True
    assert cap.get_value() is True
    with pytest.raises(ActionNotAllowed):
        await cap.set_instance_state(
            Context(),
            ToggleCapabilityInstanceActionState(instance=ToggleCapabilityInstance.IONIZATION, value=True),
        )
    with pytest.raises(ActionNotAllowed):
        await cap.set_instance_state(
            Context(),
            ToggleCapabilityInstanceActionState(instance=ToggleCapabilityInstance.IONIZATION, value=False),
        )

    cap = get_custom_capability(
        hass,
        BASIC_ENTRY_DATA,
        {
            const.CONF_ENTITY_CUSTOM_CAPABILITY_STATE_ENTITY_ID: state.entity_id,
            const.CONF_ENTITY_CUSTOM_TOGGLE_TURN_ON: {
                CONF_SERVICE: "test.turn_on",
                ATTR_ENTITY_ID: "switch.test1",
            },
            const.CONF_ENTITY_CUSTOM_TOGGLE_TURN_OFF: {
                CONF_SERVICE: "test.turn_off",
                ATTR_ENTITY_ID: "switch.test2",
            },
        },
        CapabilityType.TOGGLE,
        ToggleCapabilityInstance.IONIZATION,
        "foo",
    )
    assert cap.supported is True
    assert cap.retrievable is True
    assert cap.reportable is True
    assert cap.get_value() is True

    hass.states.async_set(state.entity_id, STATE_OFF)
    assert cap.get_value() is False

    calls_on = async_mock_service(hass, "test", "turn_on")
    await cap.set_instance_state(
        Context(),
        ToggleCapabilityInstanceActionState(instance=ToggleCapabilityInstance.IONIZATION, value=True),
    )
    assert len(calls_on) == 1
    assert calls_on[0].data == {ATTR_ENTITY_ID: "switch.test1"}

    calls_off = async_mock_service(hass, "test", "turn_off")
    await cap.set_instance_state(
        Context(),
        ToggleCapabilityInstanceActionState(instance=ToggleCapabilityInstance.IONIZATION, value=False),
    )
    assert len(calls_off) == 1
    assert calls_off[0].data == {ATTR_ENTITY_ID: "switch.test2"}

    for t in ("", STATE_UNKNOWN, "None", STATE_UNAVAILABLE):
        assert cap.new_with_value_template(Template(t)).get_value() is None

    for t in ("True", "on", "1"):
        assert cap.new_with_value_template(Template(t)).get_value() is True

    for t in ("False", "off", "0"):
        assert cap.new_with_value_template(Template(t)).get_value() is False


async def test_capability_custom_range_random_access(hass):
    state = State("switch.test", "30", {})
    hass.states.async_set(state.entity_id, state.state)
    cap = cast(
        CustomRangeCapability,
        get_custom_capability(
            hass,
            BASIC_ENTRY_DATA,
            {
                const.CONF_ENTITY_CUSTOM_CAPABILITY_STATE_ENTITY_ID: state.entity_id,
                const.CONF_ENTITY_RANGE: {
                    const.CONF_ENTITY_RANGE_MIN: 10,
                    const.CONF_ENTITY_RANGE_MAX: 50,
                    const.CONF_ENTITY_RANGE_PRECISION: 3,
                },
                const.CONF_ENTITY_CUSTOM_RANGE_SET_VALUE: {
                    CONF_SERVICE: "test.set_value",
                    ATTR_ENTITY_ID: "input_number.test",
                    CONF_SERVICE_DATA: {"value": dynamic_template("value: {{ value|int }}")},
                },
            },
            CapabilityType.RANGE,
            RangeCapabilityInstance.OPEN,
            "foo",
        ),
    )
    assert cap.supported is True
    assert cap.retrievable is True
    assert cap.reportable is True
    assert cap.support_random_access is True
    assert cap.get_value() == 30

    for v in ["55", "5"]:
        hass.states.async_set(state.entity_id, v)
        assert cap.get_value() is None

    hass.states.async_set(state.entity_id, "30")

    calls = async_mock_service(hass, "test", "set_value")
    for value, relative in ((40, False), (100, False), (10, True), (-3, True), (-50, True)):
        await cap.set_instance_state(
            Context(),
            RangeCapabilityInstanceActionState(instance=RangeCapabilityInstance.OPEN, value=value, relative=relative),
        )

    assert len(calls) == 5
    for i in range(0, len(calls)):
        assert calls[i].data[ATTR_ENTITY_ID] == "input_number.test"

    assert calls[0].data["value"] == "value: 40"
    assert calls[1].data["value"] == "value: 100"
    assert calls[2].data["value"] == "value: 40"
    assert calls[3].data["value"] == "value: 27"
    assert calls[4].data["value"] == "value: 10"

    for t in ("False", "None", STATE_UNKNOWN, STATE_UNAVAILABLE):
        assert cap.new_with_value_template(Template(t)).get_value() is None

    hass.states.async_set(state.entity_id, STATE_UNKNOWN)
    with pytest.raises(APIError) as e:
        await cap.set_instance_state(
            Context(),
            RangeCapabilityInstanceActionState(instance=RangeCapabilityInstance.OPEN, value=10, relative=True),
        )
    assert e.value.code == ResponseCode.DEVICE_OFF
    assert e.value.message == "Device switch.test probably turned off"

    hass.states.async_set(state.entity_id, STATE_UNAVAILABLE)
    with pytest.raises(APIError) as e:
        await cap.set_instance_state(
            Context(),
            RangeCapabilityInstanceActionState(instance=RangeCapabilityInstance.OPEN, value=10, relative=True),
        )
    assert e.value.code == ResponseCode.NOT_SUPPORTED_IN_CURRENT_MODE
    assert e.value.message == "Missing current value for instance open of range capability of foo"

    hass.states.async_remove(state.entity_id)
    with pytest.raises(APIError) as e:
        await cap.set_instance_state(
            Context(),
            RangeCapabilityInstanceActionState(instance=RangeCapabilityInstance.OPEN, value=10, relative=True),
        )
    assert e.value.code == ResponseCode.DEVICE_OFF
    assert e.value.message == "Entity switch.test not found"


async def test_capability_custom_range_random_access_no_state(hass):
    state = State("switch.test", "30", {})
    hass.states.async_set(state.entity_id, state.state)

    cap = cast(
        CustomRangeCapability,
        get_custom_capability(
            hass,
            BASIC_ENTRY_DATA,
            {
                const.CONF_ENTITY_RANGE: {
                    const.CONF_ENTITY_RANGE_MIN: 10,
                    const.CONF_ENTITY_RANGE_MAX: 50,
                    const.CONF_ENTITY_RANGE_PRECISION: 3,
                },
                const.CONF_ENTITY_CUSTOM_RANGE_SET_VALUE: {
                    CONF_SERVICE: "test.set_value",
                    ATTR_ENTITY_ID: "input_number.test",
                    CONF_SERVICE_DATA: {"value": dynamic_template("value: {{ value|int }}")},
                },
            },
            CapabilityType.RANGE,
            RangeCapabilityInstance.OPEN,
            "foo",
        ),
    )
    assert cap.supported is True
    assert cap.retrievable is False
    assert cap.reportable is False
    assert cap.support_random_access is True
    assert cap.get_value() is None

    calls = async_mock_service(hass, "test", "set_value")
    for value, relative in ((40, False), (100, False)):
        await cap.set_instance_state(
            Context(),
            RangeCapabilityInstanceActionState(instance=RangeCapabilityInstance.OPEN, value=value, relative=relative),
        )

    assert len(calls) == 2
    for i in range(0, len(calls)):
        assert calls[i].data[ATTR_ENTITY_ID] == "input_number.test"

    assert calls[0].data["value"] == "value: 40"
    assert calls[1].data["value"] == "value: 100"

    for v in [10, -3, 50]:
        with pytest.raises(APIError) as e:
            await cap.set_instance_state(
                Context(),
                RangeCapabilityInstanceActionState(instance=RangeCapabilityInstance.OPEN, value=v, relative=True),
            )
        assert e.value.code == ResponseCode.NOT_SUPPORTED_IN_CURRENT_MODE
        assert e.value.message == (
            "Unable to set relative value for instance open of range capability of foo: "
            "no current value source or service found"
        )


async def test_capability_custom_range_relative_override_no_state(hass):
    cap = cast(
        CustomRangeCapability,
        get_custom_capability(
            hass,
            BASIC_ENTRY_DATA,
            {
                const.CONF_ENTITY_RANGE: {
                    const.CONF_ENTITY_RANGE_MIN: 10,
                    const.CONF_ENTITY_RANGE_MAX: 99,
                    const.CONF_ENTITY_RANGE_PRECISION: 3,
                },
                const.CONF_ENTITY_CUSTOM_RANGE_SET_VALUE: {
                    CONF_SERVICE: "test.set_value",
                    ATTR_ENTITY_ID: "input_number.test",
                    CONF_SERVICE_DATA: {"value": dynamic_template("value: {{ value|int }}")},
                },
                const.CONF_ENTITY_CUSTOM_RANGE_INCREASE_VALUE: {
                    CONF_SERVICE: "test.increase_value",
                    ATTR_ENTITY_ID: "input_number.test",
                    CONF_SERVICE_DATA: {"value": dynamic_template("value: {{ value|int }}")},
                },
                const.CONF_ENTITY_CUSTOM_RANGE_DECREASE_VALUE: {
                    CONF_SERVICE: "test.decrease_value",
                    ATTR_ENTITY_ID: "input_number.test",
                    CONF_SERVICE_DATA: {"value": dynamic_template("value: {{ value|int }}")},
                },
            },
            CapabilityType.RANGE,
            RangeCapabilityInstance.OPEN,
            "foo",
        ),
    )
    assert cap.supported is True
    assert cap.support_random_access is True
    assert cap.retrievable is False
    assert cap.reportable is False
    assert cap.get_value() is None

    calls = async_mock_service(hass, "test", "set_value")
    for value, relative in ((40, False), (100, False)):
        await cap.set_instance_state(
            Context(),
            RangeCapabilityInstanceActionState(instance=RangeCapabilityInstance.OPEN, value=value, relative=relative),
        )

    assert len(calls) == 2
    for i in range(0, len(calls)):
        assert calls[i].data[ATTR_ENTITY_ID] == "input_number.test"

    assert calls[0].data["value"] == "value: 40"
    assert calls[1].data["value"] == "value: 100"

    calls = async_mock_service(hass, "test", "increase_value")
    await cap.set_instance_state(
        Context(),
        RangeCapabilityInstanceActionState(instance=RangeCapabilityInstance.OPEN, value=10, relative=True),
    )
    assert len(calls) == 1
    assert calls[0].data == {"entity_id": "input_number.test", "value": "value: 10"}

    calls = async_mock_service(hass, "test", "decrease_value")
    for value in (-3, -50):
        await cap.set_instance_state(
            Context(),
            RangeCapabilityInstanceActionState(instance=RangeCapabilityInstance.OPEN, value=value, relative=True),
        )
    assert len(calls) == 2
    assert calls[0].data == {"entity_id": "input_number.test", "value": "value: -3"}
    assert calls[1].data == {"entity_id": "input_number.test", "value": "value: -50"}


async def test_capability_custom_range_only_relative(hass):
    cap = cast(
        CustomRangeCapability,
        get_custom_capability(
            hass,
            BASIC_ENTRY_DATA,
            {
                const.CONF_ENTITY_CUSTOM_RANGE_INCREASE_VALUE: {
                    CONF_SERVICE: "test.increase_value",
                    ATTR_ENTITY_ID: "input_number.test",
                    CONF_SERVICE_DATA: {"value": dynamic_template("value: {{ value|int }}")},
                },
                const.CONF_ENTITY_CUSTOM_RANGE_DECREASE_VALUE: {
                    CONF_SERVICE: "test.decrease_value",
                    ATTR_ENTITY_ID: "input_number.test",
                    CONF_SERVICE_DATA: {"value": dynamic_template("value: {{ value|int }}")},
                },
            },
            CapabilityType.RANGE,
            RangeCapabilityInstance.OPEN,
            "foo",
        ),
    )
    assert cap.supported is True
    assert cap.support_random_access is False
    assert cap.retrievable is False
    assert cap.reportable is False
    assert cap.get_value() is None

    calls = async_mock_service(hass, "test", "increase_value")
    await cap.set_instance_state(
        Context(),
        RangeCapabilityInstanceActionState(instance=RangeCapabilityInstance.OPEN, value=10, relative=True),
    )
    assert len(calls) == 1
    assert calls[0].data == {"entity_id": "input_number.test", "value": "value: 10"}

    calls = async_mock_service(hass, "test", "decrease_value")
    for value in (-3, -50):
        await cap.set_instance_state(
            Context(),
            RangeCapabilityInstanceActionState(instance=RangeCapabilityInstance.OPEN, value=value, relative=True),
        )
    assert len(calls) == 2
    assert calls[0].data == {"entity_id": "input_number.test", "value": "value: -3"}
    assert calls[1].data == {"entity_id": "input_number.test", "value": "value: -50"}


async def test_capability_custom_range_no_service(hass):
    cap = cast(
        CustomRangeCapability,
        get_custom_capability(
            hass,
            BASIC_ENTRY_DATA,
            {},
            CapabilityType.RANGE,
            RangeCapabilityInstance.OPEN,
            "foo",
        ),
    )
    assert cap.supported is True
    assert cap.support_random_access is False
    assert cap.retrievable is False
    assert cap.reportable is False
    assert cap.get_value() is None

    with pytest.raises(ActionNotAllowed):
        await cap.set_instance_state(
            Context(),
            RangeCapabilityInstanceActionState(instance=RangeCapabilityInstance.OPEN, value=10),
        )
