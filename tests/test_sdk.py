"""Smoke tests for the installed enody-py binary, without device I/O."""

from custom_components.enody.api import _load_enody


def test_sdk_token_round_trip() -> None:
    """The real SDK can restore and serialize a stored pairing token."""
    enody = _load_enody()
    data = {
        "host_id": "98a316b1-bf8c-4000-8000-000000000001",
        "key_id": "98a316b1-bf8c-4000-8000-000000000002",
        "data": [7] * 32,
    }

    assert enody.Token.from_dict(data).to_dict() == data


def test_sdk_color_and_transition_types() -> None:
    """Native control types load on each supported Python test runtime."""
    enody = _load_enody()
    configurations = (
        enody.Configuration.blackbody(3000),
        enody.Configuration.chromatic(0.3, 0.4),
        enody.Configuration.flux(),
    )

    for configuration in configurations:
        assert isinstance(configuration, enody.Configuration)
        transition = enody.Transition.linear(
            configuration, enody.Flux.relative(0.5), 2.5
        )
        assert isinstance(transition, enody.Transition)


def test_pinned_sdk_health_bridge_bypasses_python_cache() -> None:
    """Use the real 0.2.3 wrapper; only its native transport is a test double."""
    from importlib.metadata import version
    from unittest.mock import Mock

    from enody.interface import Runtime

    from custom_components.enody.api import _read_live_host

    assert version("enody") == "0.2.3"
    native = Mock()
    native.host.return_value.fixtures.return_value = []
    runtime = Runtime.from_rs(native)
    cached = runtime.host()
    cached.fixtures()
    for _ in range(2):
        assert runtime.host() is cached
        cached.version()
        cached.fixtures()
    assert native.host.call_count == 1
    assert native.host.return_value.fixtures.call_count == 1

    for _ in range(2):
        _read_live_host(runtime)
    assert native.host.call_count == 3
    assert native.host.return_value.fixtures.call_count == 1

    native.host.side_effect = RuntimeError("dead transport")
    assert runtime.host() is cached
    import pytest

    with pytest.raises(RuntimeError, match="dead transport"):
        _read_live_host(runtime)


def test_health_bridge_reaches_installed_native_runtime() -> None:
    """The actual binary rejects a live read on an unconnected runtime."""
    import pytest
    from enody.interface import Host

    from custom_components.enody.api import _read_live_host

    enody = _load_enody()
    token = enody.Token.from_dict(
        {
            "host_id": "98a316b1-bf8c-4000-8000-000000000001",
            "key_id": "ha-test",
            "data": [7] * 32,
        }
    )
    runtime = enody.WifiConnection.runtime_from_endpoint(token, "127.0.0.1:1")
    # Seed cached metadata: no sockets are opened by this smoke test.
    cached = Host(token.host_id(), "0.2.5", [], None)
    runtime._host = cached
    assert runtime.host() is cached
    for _ in range(2):
        with pytest.raises(RuntimeError, match="Busy"):
            _read_live_host(runtime)
