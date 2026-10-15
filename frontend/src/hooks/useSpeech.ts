// Modified for the IronMan J.A.R.V.I.S. project (see NOTICE). Original: https://github.com/open-jarvis/OpenJarvis (Apache-2.0)
﻿import { useState, useCallback, useRef, useEffect } from 'react';
import { transcribeAudio, fetchSpeechHealth } from '../lib/api';

export type SpeechState = 'idle' | 'recording' | 'transcribing';

interface UseSpeechOptions {
  onAutoText?: (text: string) => void;
}

const SILENCE_THRESHOLD = 0.015; // volume below this counts as silence
const SILENCE_MS = 1500;         // stop after this much silence
const NO_SPEECH_MS = 10000;      // give up if nobody speaks at all

export function useSpeech(options: UseSpeechOptions = {}) {
  const [state, setState] = useState<SpeechState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [available, setAvailable] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const timerRef = useRef<number | null>(null);
  const onAutoTextRef = useRef(options.onAutoText);
  onAutoTextRef.current = options.onAutoText;

  useEffect(() => {
    fetchSpeechHealth()
      .then((health) => setAvailable(health.available))
      .catch(() => setAvailable(false));
  }, []);

  const stopMonitor = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    audioCtxRef.current?.close().catch(() => {});
    audioCtxRef.current = null;
  }, []);

  useEffect(() => stopMonitor, [stopMonitor]);

  const stopRecording = useCallback(async (): Promise<string> => {
    stopMonitor();
    return new Promise((resolve, reject) => {
      const recorder = mediaRecorderRef.current;
      if (!recorder || recorder.state !== 'recording') {
        reject(new Error('Not recording'));
        return;
      }

      recorder.onstop = async () => {
        setState('transcribing');

        streamRef.current?.getTracks().forEach((track) => track.stop());
        streamRef.current = null;

        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        chunksRef.current = [];

        try {
          const result = await transcribeAudio(blob);
          setState('idle');
          resolve(result.text);
        } catch (err) {
          setState('idle');
          const msg = err instanceof Error ? err.message : 'Transcription failed';
          setError(msg);
          reject(err);
        }
      };

      recorder.stop();
    });
  }, [stopMonitor]);

  const startRecording = useCallback(async (): Promise<void> => {
    setError(null);

    if (!navigator.mediaDevices?.getUserMedia) {
      setError('Microphone not supported in this browser');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.start();
      mediaRecorderRef.current = recorder;
      setState('recording');

      // --- silence detection ---
      const ctx = new AudioContext();
      audioCtxRef.current = ctx;
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      ctx.createMediaStreamSource(stream).connect(analyser);
      const data = new Float32Array(analyser.fftSize);

      const startedAt = Date.now();
      let heardSpeech = false;
      let lastLoud = Date.now();

      timerRef.current = window.setInterval(() => {
        analyser.getFloatTimeDomainData(data);
        let sum = 0;
        for (let i = 0; i < data.length; i++) sum += data[i] * data[i];
        const rms = Math.sqrt(sum / data.length);
        const now = Date.now();

        if (rms > SILENCE_THRESHOLD) {
          heardSpeech = true;
          lastLoud = now;
        }

        const silentTooLong = heardSpeech && now - lastLoud > SILENCE_MS;
        const nobodySpoke = !heardSpeech && now - startedAt > NO_SPEECH_MS;
        if (silentTooLong || nobodySpoke) {
          stopRecording()
            .then((text) => {
              if (text) onAutoTextRef.current?.(text);
            })
            .catch(() => {});
        }
      }, 100);
    } catch (err) {
      setError('Microphone access denied');
      setState('idle');
    }
  }, [stopRecording]);

  return {
    state,
    error,
    available,
    startRecording,
    stopRecording,
    isRecording: state === 'recording',
    isTranscribing: state === 'transcribing',
  };
}
