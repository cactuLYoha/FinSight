import json
from http.client import BadStatusLine, IncompleteRead, RemoteDisconnected
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

import docker_smoke


class Clock:
    def __init__(self):
        self.now = 0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(docker_smoke, 'time', clock)
    return clock


def test_ready_api_returns_without_waiting(clock):
    request = Mock(return_value={'status': 'ok'})

    docker_smoke.wait_ready(request)

    request.assert_called_once_with('/api/health', timeout=10)
    assert clock.sleeps == []


@pytest.mark.parametrize('error', [
    RemoteDisconnected('Restart closed the connection'),
    ConnectionResetError('Connection reset'),
    ConnectionAbortedError('Connection aborted'),
    URLError('Connection refused'),
    TimeoutError('Request timed out'),
    HTTPError('http://127.0.0.1:5000/api/health', 503, 'Unavailable', None, None),
    BadStatusLine('Incomplete HTTP status'),
    IncompleteRead(b'partial', 10),
])
def test_transient_errors_are_retried_until_ready(clock, error):
    request = Mock(side_effect=[error, {'status': 'ok'}])

    docker_smoke.wait_ready(request)

    assert request.call_count == 2
    assert all(call.args == ('/api/health',) for call in request.call_args_list)
    assert clock.sleeps == [2]


def test_restart_can_have_multiple_errors_and_starting_responses(clock):
    request = Mock(side_effect=[
        RemoteDisconnected('Restarting'),
        HTTPError('http://127.0.0.1:5000/api/health', 503, 'Unavailable', None, None),
        {'status': 'starting'},
        {'status': 'ok'},
    ])

    docker_smoke.wait_ready(request)

    assert request.call_count == 4
    assert clock.sleeps == [2, 2, 2]


def test_timeout_is_bounded_and_retains_last_network_error(clock):
    error = RemoteDisconnected('Still restarting')
    request = Mock(side_effect=error)

    with pytest.raises(RuntimeError, match='healthcheck did not become ready') as caught:
        docker_smoke.wait_ready(request, timeout=5)

    assert caught.value.__cause__ is error
    assert clock.now == 5
    assert clock.sleeps == [2, 2, 1]
    assert [call.kwargs['timeout'] for call in request.call_args_list] == [5, 3, 1]


def test_time_spent_in_requests_reduces_remaining_wait(clock):
    error = ConnectionResetError('Slow restart')

    def fail_slowly(path, *, timeout):
        assert path == '/api/health'
        assert timeout == 5
        clock.now += 4
        raise error

    request = Mock(side_effect=fail_slowly)
    with pytest.raises(RuntimeError) as caught:
        docker_smoke.wait_ready(request, timeout=5)

    assert caught.value.__cause__ is error
    assert request.call_count == 1
    assert clock.sleeps == [1]
    assert clock.now == 5


@pytest.mark.parametrize('response', [{}, {'unexpected': 'payload'}])
def test_invalid_health_structure_fails_without_retries(clock, response):
    request = Mock(return_value=response)

    with pytest.raises(KeyError):
        docker_smoke.wait_ready(request)

    assert request.call_count == 1
    assert clock.sleeps == []


def test_invalid_json_is_not_hidden_by_network_retries(clock):
    error = json.JSONDecodeError('Invalid health JSON', '', 0)
    request = Mock(side_effect=error)

    with pytest.raises(json.JSONDecodeError):
        docker_smoke.wait_ready(request)

    assert request.call_count == 1
    assert clock.sleeps == []
