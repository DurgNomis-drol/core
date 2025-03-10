"""Voice over IP (VoIP) implementation."""
from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterable
import logging
import time
from typing import TYPE_CHECKING

import async_timeout
from voip_utils import CallInfo, RtpDatagramProtocol, SdpInfo, VoipDatagramProtocol

from homeassistant.components import stt, tts
from homeassistant.components.assist_pipeline import (
    Pipeline,
    PipelineEvent,
    PipelineEventType,
    async_pipeline_from_audio_stream,
    select as pipeline_select,
)
from homeassistant.components.assist_pipeline.vad import VoiceCommandSegmenter
from homeassistant.const import __version__
from homeassistant.core import HomeAssistant

from .const import DOMAIN

if TYPE_CHECKING:
    from .devices import VoIPDevice, VoIPDevices

_BUFFERED_CHUNKS_BEFORE_SPEECH = 100  # ~2 seconds
_LOGGER = logging.getLogger(__name__)


class HassVoipDatagramProtocol(VoipDatagramProtocol):
    """HA UDP server for Voice over IP (VoIP)."""

    def __init__(self, hass: HomeAssistant, devices: VoIPDevices) -> None:
        """Set up VoIP call handler."""
        super().__init__(
            sdp_info=SdpInfo(
                username="homeassistant",
                id=time.monotonic_ns(),
                session_name="voip_hass",
                version=__version__,
            ),
            protocol_factory=lambda call_info: PipelineRtpDatagramProtocol(
                hass,
                hass.config.language,
                devices.async_get_or_create(call_info),
            ),
        )
        self.hass = hass
        self.devices = devices

    def is_valid_call(self, call_info: CallInfo) -> bool:
        """Filter calls."""
        device = self.devices.async_get_or_create(call_info)
        return device.async_allow_call(self.hass)


class PipelineRtpDatagramProtocol(RtpDatagramProtocol):
    """Run a voice assistant pipeline in a loop for a VoIP call."""

    def __init__(
        self,
        hass: HomeAssistant,
        language: str,
        voip_device: VoIPDevice,
        pipeline_timeout: float = 30.0,
        audio_timeout: float = 2.0,
    ) -> None:
        """Set up pipeline RTP server."""
        # STT expects 16Khz mono with 16-bit samples
        super().__init__(rate=16000, width=2, channels=1)

        self.hass = hass
        self.language = language
        self.voip_device = voip_device
        self.pipeline: Pipeline | None = None
        self.pipeline_timeout = pipeline_timeout
        self.audio_timeout = audio_timeout

        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._pipeline_task: asyncio.Task | None = None
        self._conversation_id: str | None = None

    def connection_made(self, transport):
        """Server is ready."""
        super().connection_made(transport)
        self.voip_device.set_is_active(True)

    def connection_lost(self, exc):
        """Handle connection is lost or closed."""
        super().connection_lost(exc)
        self.voip_device.set_is_active(False)

    def on_chunk(self, audio_bytes: bytes) -> None:
        """Handle raw audio chunk."""
        if self._pipeline_task is None:
            self._clear_audio_queue()

            # Run pipeline until voice command finishes, then start over
            self._pipeline_task = self.hass.async_create_background_task(
                self._run_pipeline(),
                "voip_pipeline_run",
            )

        self._audio_queue.put_nowait(audio_bytes)

    async def _run_pipeline(
        self,
    ) -> None:
        """Forward audio to pipeline STT and handle TTS."""
        _LOGGER.debug("Starting pipeline")

        async def stt_stream():
            try:
                async for chunk in self._segment_audio():
                    yield chunk
            except asyncio.TimeoutError:
                # Expected after caller hangs up
                _LOGGER.debug("Audio timeout")

                if self.transport is not None:
                    self.transport.close()
                    self.transport = None
            finally:
                self._clear_audio_queue()

        try:
            # Run pipeline with a timeout
            async with async_timeout.timeout(self.pipeline_timeout):
                await async_pipeline_from_audio_stream(
                    self.hass,
                    event_callback=self._event_callback,
                    stt_metadata=stt.SpeechMetadata(
                        language="",  # set in async_pipeline_from_audio_stream
                        format=stt.AudioFormats.WAV,
                        codec=stt.AudioCodecs.PCM,
                        bit_rate=stt.AudioBitRates.BITRATE_16,
                        sample_rate=stt.AudioSampleRates.SAMPLERATE_16000,
                        channel=stt.AudioChannels.CHANNEL_MONO,
                    ),
                    stt_stream=stt_stream(),
                    pipeline_id=pipeline_select.get_chosen_pipeline(
                        self.hass, DOMAIN, self.voip_device.voip_id
                    ),
                    conversation_id=self._conversation_id,
                    tts_options={tts.ATTR_AUDIO_OUTPUT: "raw"},
                )

        except asyncio.TimeoutError:
            # Expected after caller hangs up
            _LOGGER.debug("Pipeline timeout")

            if self.transport is not None:
                self.transport.close()
                self.transport = None
        finally:
            # Allow pipeline to run again
            self._pipeline_task = None

    async def _segment_audio(self) -> AsyncIterable[bytes]:
        segmenter = VoiceCommandSegmenter()
        chunk_buffer: deque[bytes] = deque(maxlen=_BUFFERED_CHUNKS_BEFORE_SPEECH)

        # Timeout if no audio comes in for a while.
        # This means the caller hung up.
        async with async_timeout.timeout(self.audio_timeout):
            chunk = await self._audio_queue.get()

        while chunk:
            if not segmenter.process(chunk):
                # Voice command is finished
                break

            if segmenter.in_command:
                if chunk_buffer:
                    # Release audio in buffer first
                    for buffered_chunk in chunk_buffer:
                        yield buffered_chunk

                    chunk_buffer.clear()

                yield chunk
            else:
                # Buffer until command starts
                chunk_buffer.append(chunk)

            async with async_timeout.timeout(self.audio_timeout):
                chunk = await self._audio_queue.get()

    def _clear_audio_queue(self) -> None:
        while not self._audio_queue.empty():
            self._audio_queue.get_nowait()

    def _event_callback(self, event: PipelineEvent):
        if not event.data:
            return

        if event.type == PipelineEventType.INTENT_END:
            # Capture conversation id
            self._conversation_id = event.data["intent_output"]["conversation_id"]
        elif event.type == PipelineEventType.TTS_END:
            # Send TTS audio to caller over RTP
            media_id = event.data["tts_output"]["media_id"]
            self.hass.async_create_background_task(
                self._send_media(media_id),
                "voip_pipeline_tts",
            )

    async def _send_media(self, media_id: str) -> None:
        """Send TTS audio to caller via RTP."""
        if self.transport is None:
            return

        _extension, audio_bytes = await tts.async_get_media_source_audio(
            self.hass,
            media_id,
        )

        _LOGGER.debug("Sending %s byte(s) of audio", len(audio_bytes))

        # Assume TTS audio is 16Khz 16-bit mono
        await self.send_audio(audio_bytes, rate=16000, width=2, channels=1)
