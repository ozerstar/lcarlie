import { Room, RoomEvent, Track, AudioPresets, createLocalAudioTrack } from 'livekit-client';

export function createVoiceRoom({ onStatus, onTranscript, onEnded }) {
  let room = null;
  let audio = null;
  let generation = 0;
  let microphone = null;
  const transcripts = new Set();

  function prepare() {
    if (!microphone) microphone = createLocalAudioTrack({
      echoCancellation: true, noiseSuppression: true, autoGainControl: true,
    });
    return microphone;
  }

  function waitForAgent(next) {
    if (next.remoteParticipants.size) return Promise.resolve();
    return new Promise((resolve, reject) => {
      function cleanup() {
        clearTimeout(timer);
        next.off(RoomEvent.ParticipantConnected, joined);
        next.off(RoomEvent.Disconnected, disconnected);
      }
      const timer = setTimeout(() => {
        cleanup();
        reject(new Error('Jarvis ses işçisi bağlanamadı'));
      }, 15000);
      function disconnected() {
        cleanup();
        reject(new Error('Ses bağlantısı kesildi'));
      }
      function joined() {
        cleanup();
        resolve();
      }
      next.on(RoomEvent.ParticipantConnected, joined);
      next.on(RoomEvent.Disconnected, disconnected);
      if (next.remoteParticipants.size) joined();
    });
  }

  async function stop() {
    generation += 1;
    const old = room;
    room = null;
    const pendingMicrophone = microphone;
    microphone = null;
    if (pendingMicrophone) {
      try { (await pendingMicrophone).stop(); } catch (_) { /* denied permission */ }
    }
    if (old) {
      try { await old.localParticipant.setMicrophoneEnabled(false); } catch (_) { /* device gone */ }
      try { await old.disconnect(); } catch (_) { /* already disconnected */ }
    }
    audio?.remove();
    audio = null;
    transcripts.clear();
  }

  async function start(url, token) {
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
      if (current !== generation) { await next.disconnect(); return; }
      await waitForAgent(next);
      if (current !== generation) { await next.disconnect(); return; }
      const track = await prepare();
      if (current !== generation) { track.stop(); await next.disconnect(); return; }
      await next.localParticipant.publishTrack(track, { source: Track.Source.Microphone });
      if (current !== generation) { await next.disconnect(); return; }
      onStatus('Dinliyor · Gerçek zamanlı görüşme');
    } catch (error) {
      await stop();
      throw error;
    }
  }

  return { prepare, start, stop, get active() { return Boolean(room); } };
}
