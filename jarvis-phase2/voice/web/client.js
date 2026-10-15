import { Room, RoomEvent, Track, AudioPresets } from 'livekit-client';

export function createVoiceRoom({ onStatus, onTranscript, onEnded }) {
  let room = null;
  let audio = null;
  let generation = 0;
  const transcripts = new Set();

  async function stop() {
    generation += 1;
    const old = room;
    room = null;
    if (old) {
      try { await old.localParticipant.setMicrophoneEnabled(false); } catch (_) { /* device gone */ }
      await old.disconnect();
    }
    audio?.remove();
    audio = null;
    transcripts.clear();
  }

  async function start(url, token) {
    await stop();
    const current = ++generation;
    const next = new Room({ adaptiveStream: false, dynacast: false,
      audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      publishDefaults: { audioPreset: AudioPresets.speech, dtx: true } });
    room = next;
    next.on(RoomEvent.TrackSubscribed, (track) => {
      if (current !== generation || track.kind !== Track.Kind.Audio) return;
      const element = track.attach();
      element.autoplay = true;
      element.setAttribute('playsinline', '');
      element.hidden = true;
      document.body.append(element);
      audio = element;
      element.play().catch(() => onStatus('Sesi açmak için ekrana dokunun'));
    });
    next.on(RoomEvent.TrackUnsubscribed, (track) => {
      track.detach().forEach((element) => element.remove());
      if (audio && !audio.isConnected) audio = null;
    });
    next.on(RoomEvent.TranscriptionReceived, (segments, participant) => {
      if (current !== generation) return;
      for (const segment of segments) {
        if (!segment.final || !segment.text?.trim() || transcripts.has(segment.id)) continue;
        transcripts.add(segment.id);
        onTranscript(participant?.isLocal ? 'user' : 'jarvis', segment.text.trim());
      }
    });
    next.on(RoomEvent.Reconnecting, () => onStatus('Ses bağlantısı yenileniyor'));
    next.on(RoomEvent.Reconnected, () => onStatus('Sesli görüşme sürüyor'));
    next.on(RoomEvent.Disconnected, () => {
      if (current === generation) {
        stop();
        onEnded('Ses bağlantısı kesildi; konuşma yeniden gönderilmedi');
      }
    });
    try {
      await next.connect(url, token, { autoSubscribe: true });
      if (current !== generation) return;
      await next.localParticipant.setMicrophoneEnabled(true, {
        echoCancellation: true, noiseSuppression: true, autoGainControl: true,
      });
      if (current !== generation) return;
      onStatus('Dinliyor · Gerçek zamanlı görüşme');
    } catch (error) {
      await stop();
      throw error;
    }
  }

  return { start, stop, get active() { return Boolean(room); } };
}
