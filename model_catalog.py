"""Transcription models exposed by the app, without importing PyTorch."""

MODEL_CHOICES = {
    "RNNT": "v3_e2e_rnnt",
    "CTC": "v3_e2e_ctc",
    "Multilingual CTC (220M)": "multilingual_ctc",
    "Multilingual CTC Large (600M)": "multilingual_large_ctc",
}

DEFAULT_BUNDLED_MODELS = ("v3_e2e_rnnt", "v3_e2e_ctc")


def model_files(model_name):
    """Required bundle/cache files; multilingual CTC uses an embedded alphabet."""
    if model_name not in MODEL_CHOICES.values():
        raise ValueError(f"Unsupported transcription model: {model_name}")
    files = (f"{model_name}.ckpt",)
    if model_name in DEFAULT_BUNDLED_MODELS:
        files += (f"{model_name}_tokenizer.model",)
    return files
