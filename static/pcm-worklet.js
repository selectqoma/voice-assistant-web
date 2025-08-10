class PCMWorkletProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
  }

  process(inputs) {
    const input = inputs[0];
    if (input && input[0]) {
      const channel = input[0];
      const length = channel.length;
      const pcmBuffer = new ArrayBuffer(length * 2);
      const view = new DataView(pcmBuffer);
      for (let i = 0; i < length; i++) {
        let s = Math.max(-1, Math.min(1, channel[i]));
        view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      }
      this.port.postMessage(pcmBuffer, [pcmBuffer]);
    }
    return true;
  }
}

registerProcessor('pcm-worklet', PCMWorkletProcessor);


