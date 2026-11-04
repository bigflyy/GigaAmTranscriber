"""Make an fp16-compute copy of an exported encoder (plan item B2, measurement code).

    python experiments/onnx_runtime/fp16_encoder.py models/v3_e2e_rnnt/encoder.onnx OUT.onnx [OP ...]

Needs onnx (requirements-export.txt). Every float tensor becomes float16 except:
  - the log-mel front-end (/mel/ nodes): log() of powers near 1e-9 is out of fp16 range;
  - the frame-length arithmetic (nodes reached from wav_len but not from wav):
    fp16 holds whole numbers exactly only up to 2048;
  - any op types named on the command line (e.g. Softmax LayerNormalization).
Graph inputs and outputs stay float32, so the app can load the result unchanged.

onnxconverter-common's float16 converter was tried first. It left the graph's own
Cast(to=float) nodes in fp32 and produced type errors or all-NaN output, so this
script does the conversion explicitly, with casts only at region borders.

Result on 2026-11-05 (RNNT, 2 h of audio, see HANDOFF.md): text not identical
to fp32, so the app keeps fp32.
"""

import sys

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper, shape_inference

FLOAT, HALF = TensorProto.FLOAT, TensorProto.FLOAT16
FP16_LIMIT = 65504  # largest finite float16


def restore_fp32_initializers(graph):
    """Undo tools/export_models.py's fp16 storage: Cast(X__fp16) -> X becomes an fp32 initializer X."""
    initializers = {t.name: t for t in graph.initializer}
    storage_casts = [n for n in graph.node
                     if n.op_type == "Cast" and n.name.endswith("__cast") and n.input[0] in initializers]
    for node in storage_casts:
        tensor = initializers.pop(node.input[0])
        values = numpy_helper.to_array(tensor).astype(np.float32)
        tensor.CopyFrom(numpy_helper.from_array(values, node.output[0]))
        graph.node.remove(node)


def element_types(model):
    """Element type of every tensor, from shape inference on the fp32 graph."""
    inferred = shape_inference.infer_shapes(model).graph
    types = {v.name: v.type.tensor_type.elem_type
             for v in list(inferred.value_info) + list(inferred.input) + list(inferred.output)}
    types.update({t.name: t.data_type for t in model.graph.initializer})
    for node in model.graph.node:
        if node.op_type == "Constant":
            types[node.output[0]] = node.attribute[0].t.data_type
    return types


def reachable_nodes(graph, start):
    """Names of all nodes that depend on the tensor 'start'."""
    seen, tensors, changed = set(), {start}, True
    while changed:
        changed = False
        for node in graph.node:
            if node.name not in seen and any(name in tensors for name in node.input):
                seen.add(node.name)
                tensors.update(node.output)
                changed = True
    return seen


def to_half(values):
    return np.clip(values, -FP16_LIMIT, FP16_LIMIT).astype(np.float16)


def topological(nodes, available):
    """Order nodes so every input is produced before it is used (ONNX requires it)."""
    ready, pending, ordered = set(available), list(nodes), []
    while pending:
        waiting = []
        for node in pending:
            if all(not name or name in ready for name in node.input):
                ordered.append(node)
                ready.update(node.output)
            else:
                waiting.append(node)
        if len(waiting) == len(pending):
            raise RuntimeError("Cycle or missing input at " + waiting[0].name)
        pending = waiting
    return ordered


def convert(source, target, fp32_op_types=()):
    model = onnx.load(source)
    graph = model.graph
    restore_fp32_initializers(graph)
    types = element_types(model)

    length_only = reachable_nodes(graph, "wav_len") - reachable_nodes(graph, "wav")
    blocked = {n.name for n in graph.node
               if n.name.startswith("/mel/") or n.name in length_only or n.op_type in fp32_op_types}
    initializers = {t.name: t for t in graph.initializer}
    constants = {n.output[0]: n for n in graph.node if n.op_type == "Constant"}
    producer = {name: n for n in graph.node for name in n.output}
    new_initializers, new_nodes, half_names, float_names = [], [], {}, {}

    def in_half_region(name):
        node = producer.get(name)
        return node is not None and node.op_type != "Constant" and node.name not in blocked

    def half_source(name):
        """fp16 version of a float tensor, for a consumer in the fp16 region."""
        if name not in half_names:
            half = name + "__h"
            if name in initializers:
                values = numpy_helper.to_array(initializers[name])
                new_initializers.append(numpy_helper.from_array(to_half(values), half))
            elif name in constants:
                values = numpy_helper.to_array(constants[name].attribute[0].t)
                new_nodes.append(helper.make_node("Constant", [], [half], name=constants[name].name + "__h",
                                                  value=numpy_helper.from_array(to_half(values))))
            else:  # produced in the fp32 region or a graph input: cast at the border
                new_nodes.append(helper.make_node("Cast", [name], [half], to=HALF, name=name + "__to16"))
            half_names[name] = half
        return half_names[name]

    def float_source(name):
        """fp32 version of an fp16-region tensor, for a consumer in the fp32 region."""
        if name not in float_names:
            float_names[name] = name + "__f"
            new_nodes.append(helper.make_node("Cast", [name], [name + "__f"], to=FLOAT, name=name + "__to32"))
        return float_names[name]

    for node in graph.node:
        if node.op_type == "Constant":
            continue
        for index, name in enumerate(node.input):
            if not name or types.get(name) != FLOAT:
                continue
            if node.name in blocked:
                if in_half_region(name):
                    node.input[index] = float_source(name)
            elif not in_half_region(name):
                node.input[index] = half_source(name)
        if node.name in blocked:
            continue
        for attribute in node.attribute:
            if node.op_type == "Cast" and attribute.name == "to" and attribute.i == FLOAT:
                attribute.i = HALF
            elif node.op_type == "ConstantOfShape" and attribute.name == "value" and attribute.t.data_type == FLOAT:
                attribute.t.CopyFrom(numpy_helper.from_array(to_half(numpy_helper.to_array(attribute.t))))
            elif attribute.type == onnx.AttributeProto.TENSOR and attribute.t.data_type == FLOAT:
                raise RuntimeError(f"Unhandled float tensor attribute in {node.name}")

    # Graph outputs stay fp32: rename the fp16 tensor inside and cast it back.
    for output in graph.output:
        if types.get(output.name) == FLOAT and in_half_region(output.name):
            inner = output.name + "__out16"
            for node in graph.node:
                node.output[:] = [inner if name == output.name else name for name in node.output]
                node.input[:] = [inner if name == output.name else name for name in node.input]
            new_nodes.append(helper.make_node("Cast", [inner], [output.name], to=FLOAT,
                                              name=output.name + "__to32"))

    graph.initializer.extend(new_initializers)
    used = {name for node in list(graph.node) + new_nodes for name in node.input} | {o.name for o in graph.output}
    kept_initializers = [t for t in graph.initializer if t.name in used]
    nodes = [n for n in list(graph.node) + new_nodes if n.op_type != "Constant" or n.output[0] in used]
    del graph.initializer[:]
    graph.initializer.extend(kept_initializers)
    del graph.node[:]
    graph.node.extend(topological(nodes, [i.name for i in graph.input] + [t.name for t in kept_initializers]))
    del graph.value_info[:]
    onnx.checker.check_model(model)
    onnx.save(model, target)
    print(f"{len(blocked)} nodes kept in fp32, {len(new_initializers)} weights in fp16, wrote {target}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    convert(sys.argv[1], sys.argv[2], tuple(sys.argv[3:]))
