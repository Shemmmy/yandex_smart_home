from http import HTTPStatus

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entityfilter
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, MockUser
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator
from syrupy import SnapshotAssertion

from custom_components.yandex_smart_home import DOMAIN, ConnectionType, const
from custom_components.yandex_smart_home.config_flow import ConfigFlowHandler


async def test_diagnostics(
    hass_platform: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_admin_user: MockUser,
    snapshot: SnapshotAssertion,
) -> None:
    hass = hass_platform
    yaml_config = {
        "filter": {"include_domains": ["light", "sensor", "binary_sensor"]},
        "entity_config": {
            "switch.with_template": {"error_code_template": '{{ "a" + "b" }}'},
            "light.kitchen": {"properties": [{"type": "temperature", "entity": "sensor.invalid"}]},
        },
        "notifier": [{"skill_id": "foo", "oauth_token": "token", "user_id": hass_admin_user.id}],
    }
    assert await async_setup_component(hass, "diagnostics", {})
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: yaml_config})

    hass.states.async_set("sensor.invalid", "foo")
    config_entry = MockConfigEntry(
        entry_id="fe76008998bdad631c33d60ef044b9ac",
        domain=DOMAIN,
        version=ConfigFlowHandler.VERSION,
        data={
            const.CONF_CONNECTION_TYPE: ConnectionType.DIRECT,
            const.CONF_CLOUD_INSTANCE: {const.CONF_CLOUD_INSTANCE_PASSWORD: "foo"},
        },
        options={const.CONF_FILTER: {entityfilter.CONF_INCLUDE_ENTITY_GLOBS: ["*"]}},
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    client = await hass_client()
    response = await client.get(f"/api/diagnostics/config_entry/{config_entry.entry_id}")
    assert response.status == HTTPStatus.OK
    diagnostics = await response.json()
    for k in ("integration_manifest", "custom_components", "home_assistant"):
        diagnostics.pop(k, None)

    assert diagnostics == snapshot
