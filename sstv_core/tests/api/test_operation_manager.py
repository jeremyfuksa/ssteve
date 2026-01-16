import asyncio

import pytest

from sstv_core.api.models import DecodeState, TransmitState
from sstv_core.api.operation_manager import operation_manager
from sstv_core.api.session_manager import session_manager


@pytest.fixture(autouse=True)
def reset_session_manager():
    session_manager.reset()
    yield
    session_manager.reset()


@pytest.fixture(autouse=True)
async def cleanup_operations():
    await operation_manager.stop_all()
    yield
    await operation_manager.stop_all()


@pytest.mark.asyncio
async def test_decode_worker_completes():
    session = await session_manager.create_decode_session()

    operation_manager.start_decode(session)

    # Wait for worker to complete (with timeout protection)
    await operation_manager.wait_for_decode(session.session_id, timeout=2.0)

    updated = await session_manager.get_decode_session(session.session_id)
    assert updated is not None
    assert updated.state == DecodeState.COMPLETED.value
    assert updated.metadata["progress_percent"] == 100.0


@pytest.mark.asyncio
async def test_stop_decode_cancels_worker():
    session = await session_manager.create_decode_session()
    operation_manager.start_decode(session)

    # Let it run for a couple scanlines, then stop
    await asyncio.sleep(operation_manager.DECODE_LINE_DELAY * 2)
    await operation_manager.stop_decode(session.session_id)

    updated = await session_manager.get_decode_session(session.session_id)
    assert updated is not None
    assert updated.state == DecodeState.STOPPED.value


@pytest.mark.asyncio
async def test_transmit_worker_completes():
    session = await session_manager.create_transmit_session()
    operation_manager.start_transmit(session)

    # Wait for worker to complete (with timeout protection)
    await operation_manager.wait_for_transmit(session.session_id, timeout=2.0)

    updated = await session_manager.get_transmit_session(session.session_id)
    assert updated is not None
    assert updated.state == TransmitState.COMPLETED.value
    assert updated.metadata["progress_percent"] == 100.0


@pytest.mark.asyncio
async def test_cancel_transmit_worker():
    session = await session_manager.create_transmit_session()
    operation_manager.start_transmit(session)

    # Let it run for a couple scanlines, then cancel
    await asyncio.sleep(operation_manager.TRANSMIT_LINE_DELAY * 2)
    await operation_manager.stop_transmit(session.session_id)

    updated = await session_manager.get_transmit_session(session.session_id)
    assert updated is not None
    assert updated.state == TransmitState.CANCELLED.value
