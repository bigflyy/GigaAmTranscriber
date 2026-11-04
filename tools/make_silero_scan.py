"""Build models/silero_vad_scan.onnx: Silero VAD looping over many windows in one call.

Silero is recurrent and has to see the windows in order. Calling it from
Python once per 32 ms window costs about 0.2 ms of overhead per call, which
made the speech search the slowest stage on GPU. This wraps the unchanged
16 kHz model (silero_vad_16k_op15.onnx from the silero-vad package, MIT
licence) in an ONNX Scan loop, so ONNX Runtime iterates in C++ over a block
of windows and carries the state itself. The arithmetic per window is the
same; the tool checks that the outputs are identical.

Usage (needs onnx, onnxruntime, numpy and silero-vad 6.2.1 installed):
    python tools/make_silero_scan.py --out models/silero_vad_scan.onnx
"""

import argparse
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper
import onnxruntime as ort

WINDOW, CONTEXT, STATE = 512, 64, 128


def source_model():
    import silero_vad
    return Path(silero_vad.__file__).parent / "data" / "silero_vad_16k_op15.onnx"


def build(source, out):
    model = onnx.load(str(source))
    body = model.graph
    names = [item.name for item in body.input]
    if names != ["input", "state", "sr"]:
        raise ValueError(f"Unexpected Silero inputs: {names}")
    # Inside the loop the sample rate is a constant, and the inputs are
    # (carried state, one window); the outputs are (new state, probability).
    sr_constant = helper.make_node("Constant", [], ["sr"], value=helper.make_tensor("sr_value", TensorProto.INT64, [], [16000]))
    body.node.insert(0, sr_constant)
    state_in = helper.make_tensor_value_info("state", TensorProto.FLOAT, [2, 1, STATE])
    window_in = helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, CONTEXT + WINDOW])
    del body.input[:]
    body.input.extend([state_in, window_in])
    outputs = {item.name: item for item in body.output}
    state_out = helper.make_tensor_value_info("stateN", TensorProto.FLOAT, [2, 1, STATE])
    prob_out = helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, 1])
    if set(outputs) != {"output", "stateN"}:
        raise ValueError(f"Unexpected Silero outputs: {list(outputs)}")
    del body.output[:]
    body.output.extend([state_out, prob_out])
    body.name = "silero_step"

    scan = helper.make_node("Scan", ["state", "windows"], ["state_out", "probabilities"],
                            body=body, num_scan_inputs=1)
    graph = helper.make_graph(
        [scan], "silero_vad_scan",
        [helper.make_tensor_value_info("state", TensorProto.FLOAT, [2, 1, STATE]),
         helper.make_tensor_value_info("windows", TensorProto.FLOAT, ["windows", 1, CONTEXT + WINDOW])],
        [helper.make_tensor_value_info("state_out", TensorProto.FLOAT, [2, 1, STATE]),
         helper.make_tensor_value_info("probabilities", TensorProto.FLOAT, ["windows", 1, 1])])
    wrapped = helper.make_model(graph, opset_imports=model.opset_import, producer_name="gigaam_app")
    wrapped.ir_version = model.ir_version
    onnx.checker.check_model(wrapped)
    onnx.save(wrapped, str(out))


def verify(source, out):
    """Probabilities from the loop must equal one-call-per-window probabilities exactly."""
    rng = np.random.default_rng(0)
    audio = (rng.standard_normal(16000 * 20) * np.repeat(rng.random(40) > 0.5, 8000) * 0.3).astype(np.float32)
    n = len(audio) // WINDOW
    padded = np.concatenate([np.zeros(CONTEXT, np.float32), audio])
    windows = np.stack([padded[i * WINDOW:i * WINDOW + CONTEXT + WINDOW] for i in range(n)])
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    step = ort.InferenceSession(str(source), options, providers=["CPUExecutionProvider"])
    state = np.zeros((2, 1, STATE), np.float32)
    expected = []
    for window in windows:
        probability, state = step.run(None, {"input": window[None], "state": state,
                                             "sr": np.array(16000, np.int64)})
        expected.append(probability[0, 0])
    loop = ort.InferenceSession(str(out), options, providers=["CPUExecutionProvider"])
    state = np.zeros((2, 1, STATE), np.float32)
    actual = []
    for begin in range(0, n, 100):  # several calls, so the carried state is tested too
        _, probabilities = None, None
        state, probabilities = loop.run(None, {"state": state, "windows": windows[begin:begin + 100, None]})
        actual += probabilities[:, 0, 0].tolist()
    difference = float(np.abs(np.array(actual) - np.array(expected)).max())
    print(f"max |scan - per-window| = {difference:.2e} over {n} windows")
    if difference > 1e-6:
        raise RuntimeError("Scan model does not reproduce Silero")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "models" / "silero_vad_scan.onnx")
    args = parser.parse_args()
    source = source_model()
    build(source, args.out)
    verify(source, args.out)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
