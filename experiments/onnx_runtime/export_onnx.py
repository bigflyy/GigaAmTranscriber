"""Export GigaAM ASR to ONNX: wav -> (preprocessor+encoder), plus RNNT decoder/joint or CTC head."""
import sys, json, warnings
sys.path.insert(0, r"C:\MyProjects\GigaAmTranscriber")
import torch, gigaam
from torch import nn

name, out = sys.argv[1], sys.argv[2]
model = gigaam.load_model(name, device="cpu", fp16_encoder=False).float().eval()
print("params(M):", sum(p.numel() for p in model.parameters()) / 1e6)

class ConvMel(nn.Module):
    """Log-mel identical to torchaudio MelSpectrogram+SpecScaler, built from exportable ops."""
    def __init__(self, fe):
        super().__init__()
        mel = fe.featurizer[0]; spec = mel.spectrogram
        n_fft, self.hop, self.pad = spec.n_fft, spec.hop_length, spec.n_fft // 2
        self.center = spec.center
        assert spec.power == 2.0 and not spec.normalized and spec.win_length == n_fft
        window = spec.window.double()
        k = torch.arange(n_fft, dtype=torch.float64)
        f = torch.arange(n_fft // 2 + 1, dtype=torch.float64)
        ang = 2 * torch.pi * f[:, None] * k[None, :] / n_fft
        basis = torch.cat([torch.cos(ang) * window, -torch.sin(ang) * window]).float()
        self.register_buffer("basis", basis.unsqueeze(1))      # (2F, 1, n_fft)
        self.register_buffer("fb", mel.mel_scale.fb.T.contiguous())  # (n_mels, F)
        self.nf = n_fft // 2 + 1
    def forward(self, wav):
        x = wav.unsqueeze(1)
        if self.center:
            x = nn.functional.pad(x, (self.pad, self.pad), mode="reflect")
        y = nn.functional.conv1d(x, self.basis, stride=self.hop)
        power = y[:, :self.nf] ** 2 + y[:, self.nf:] ** 2
        return torch.log(torch.matmul(self.fb, power).clamp(1e-9, 1e9))

class Frontend(nn.Module):
    """Raw 16 kHz waveform batch -> encoder output (B, D, T) and lengths; for CTC also log-probs."""
    def __init__(self, m, ctc):
        super().__init__(); self.m, self.ctc = m, ctc
        self.mel = ConvMel(m.preprocessor)
    def forward(self, wav, wav_len):
        feats, flen = self.mel(wav), self.m.preprocessor.out_len(wav_len)
        enc, elen = self.m.encoder(feats, flen)
        if self.ctc:
            return self.m.head(encoder_output=enc), elen
        return enc, elen

ctc = "ctc" in name
_x = torch.randn(2, 16000 * 3)
_ref = model.preprocessor(_x, torch.tensor([48000, 48000]))[0]
_new = ConvMel(model.preprocessor)(_x)
print("mel max abs diff vs torchaudio:", (_ref - _new).abs().max().item(), _ref.shape, _new.shape)
wav = torch.randn(2, 16000 * 8); wl = torch.tensor([16000 * 8, 16000 * 5])
with warnings.catch_warnings(), torch.no_grad():
    warnings.simplefilter("ignore")
    torch.onnx.export(Frontend(model, ctc), (wav, wl), f"{out}/{name}_encoder.onnx",
        input_names=["wav", "wav_len"], output_names=["log_probs" if ctc else "encoded", "encoded_len"],
        dynamic_axes={"wav": {0: "B", 1: "N"}, "wav_len": {0: "B"},
                      ("log_probs" if ctc else "encoded"): {0: "B", (1 if ctc else 2): "T"}, "encoded_len": {0: "B"}},
        opset_version=17, dynamo=False)
    if not ctc:
        import numpy as np
        dec, joint = model.head.decoder, model.head.joint
        assert dec.lstm.num_layers == 1, dec.lstm.num_layers
        np.savez(f"{out}/{name}_head.npz",
                 embed=dec.embed.weight.numpy(),
                 w_ih=dec.lstm.weight_ih_l0.numpy(), w_hh=dec.lstm.weight_hh_l0.numpy(),
                 b=(dec.lstm.bias_ih_l0 + dec.lstm.bias_hh_l0).numpy(),
                 enc_w=joint.enc.weight.numpy(), enc_b=joint.enc.bias.numpy(),
                 pred_w=joint.pred.weight.numpy(), pred_b=joint.pred.bias.numpy(),
                 out_w=joint.joint_net[1].weight.numpy(), out_b=joint.joint_net[1].bias.numpy(),
                 blank_id=np.int64(model.decoding.blank_id))
print("ok")
