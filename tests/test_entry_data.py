from unittest.mock import patch

from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.yandex_smart_home import DOMAIN, YandexSmartHome, const
from custom_components.yandex_smart_home.entry_data import ConfigEntryData
from custom_components.yandex_smart_home.helpers import APIError
from custom_components.yandex_smart_home.schema import ResponseCode

from . import MockConfigEntryData, generate_entity_filter


def test_entry_data_unknown_version(hass):
    entry_data = ConfigEntryData(hass, MockConfigEntry())
    assert entry_data.version == "unknown"


def test_entry_data_trackable_states(hass, caplog):
    entry_data = MockConfigEntryData(
        hass=hass,
        entity_config={
            "sensor.outside_temp": {
                const.CONF_ENTITY_CUSTOM_TOGGLES: {
                    "pause": {const.CONF_ENTITY_CUSTOM_CAPABILITY_STATE_ENTITY_ID: "binary_sensor.pause"}
                },
            }
        },
        entity_filter=generate_entity_filter(include_entity_globs=["*"]),
    )

    with patch(
        "custom_components.yandex_smart_home.entry_data.get_custom_capability",
        side_effect=APIError(ResponseCode.INTERNAL_ERROR, "foo"),
    ):
        assert entry_data._get_trackable_states() == {}
    assert caplog.messages == ["Failed to track custom capability: foo"]


async def test_deprecated_pressure_unit(hass, config_entry_direct):
    issue_registry = ir.async_get(hass)

    config_entry_direct.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry_direct.entry_id)
    await hass.async_block_till_done()
    assert issue_registry.async_get_issue(DOMAIN, "deprecated_pressure_unit") is None
    await hass.config_entries.async_unload(config_entry_direct.entry_id)

    component: YandexSmartHome = hass.data[DOMAIN]
    component._yaml_config = {const.CONF_SETTINGS: {const.CONF_PRESSURE_UNIT: "foo"}}
    await hass.config_entries.async_setup(config_entry_direct.entry_id)
    assert issue_registry.async_get_issue(DOMAIN, "deprecated_pressure_unit") is not None
    await hass.config_entries.async_unload(config_entry_direct.entry_id)

    component._yaml_config = {const.CONF_SETTINGS: {}}
    await hass.config_entries.async_setup(config_entry_direct.entry_id)
    assert issue_registry.async_get_issue(DOMAIN, "deprecated_pressure_unit") is None
    await hass.config_entries.async_unload(config_entry_direct.entry_id)
