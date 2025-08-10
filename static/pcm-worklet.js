class PCMWorkletProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.targetRate = 16000;
    this.srcRate = sampleRate; // AudioContext sample rate
    this.port.onmessage = (e) => {
      if (e.data && e.data.targetRate) {
        this.targetRate = e.data.targetRate;
      }
    };
  }

  process(inputs) {
    const input = inputs[0];
    if (!(input && input[0])) return true;

    const channel = input[0];
    const src = channel;
    const ratio = this.srcRate / this.targetRate;
    if (ratio <= 1.01 && ratio >= 0.99) {
      // No resample needed; just convert to PCM16
      const len = src.length;
      const pcmBuffer = new ArrayBuffer(len * 2);
      const view = new DataView(pcmBuffer);
      for (let i = 0; i < len; i++) {
        let s = Math.max(-1, Math.min(1, src[i]));
        view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      }
      this.port.postMessage(pcmBuffer, [pcmBuffer]);
      return true;
    }

    // Downsample by linear interpolation and then convert to PCM16
    const outLen = Math.floor(src.length / ratio);
    const pcmBuffer = new ArrayBuffer(outLen * 2);
    const view = new DataView(pcmBuffer);
    let pos = 0;
    for (let i = 0; i < outLen; i++) {
      const idx = i * ratio;
      const idx0 = Math.floor(idx);
      const idx1 = Math.min(idx0 + 1, src.length - 1);
      const frac = idx - idx0;
      const sample = src[idx0] * (1 - frac) + src[idx1] * frac;
      let s = Math.max(-1, Math.min(1, sample));
      view.setInt16(pos, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      pos += 2;
    }
    this.port.postMessage(pcmBuffer, [pcmBuffer]);
    return true;
  }
}

registerProcessor('pcm-worklet', PCMWorkletProcessor);


