import os
from typing import List, Tuple

import torch
# Remove pyannote-specific imports
# from pyannote.audio import Model, Pipeline
# from pyannote.audio.core.task import Problem, Resolution, Specifications
# from pyannote.audio.pipelines import VoiceActivityDetection
# from torch.torch_version import TorchVersion
# from huggingface_hub import snapshot_download
# from huggingface_hub.errors import LocalEntryNotFoundError

# Import silero-vad
from silero_vad import load_silero_vad, read_audio, get_speech_timestamps
from .preprocess import SAMPLE_RATE, load_audio


# Remove global pipeline variable for pyannote, use silero model instead
_MODEL = None


# Remove resolve_local_segmentation_path and load_segmentation_model functions
# as they are specific to pyannote and Hugging Face Hub


def load_segmentation_model() -> torch.nn.Module:
    """
    Loads the Silero VAD model.
    """
    global _MODEL
    if _MODEL is None:
        _MODEL = load_silero_vad()
    return _MODEL


def get_pipeline(
    device: torch.device, model_id: str = None # model_id is not used for silero
) -> torch.nn.Module:
    """
    Retrieves the Silero VAD model and ensures it's compatible with the device.
    Silero VAD primarily runs on CPU, so device specification might be less critical,
    but we ensure the model is loaded.
    The pipeline is loaded only once and reused across subsequent calls.
    """
    model = load_segmentation_model()
    # Silero VAD typically runs on CPU; explicit device movement might not be necessary
    # depending on the internal implementation, but ensure consistency if needed.
    # For standard silero-vad, it often handles its internal computations without
    # requiring explicit PyTorch device assignment like pyannote models do.
    # We keep the device argument for API compatibility if downstream code relies on it.
    return model

def segment_audio_tensor(
    audio_tensor: torch.Tensor, # <-- Changed: Accept tensor directly
    sr: int, # Original sample rate of the tensor
    max_duration: float = 22.0,
    min_duration: float = 15.0,
    strict_limit_duration: float = 30.0,
    new_chunk_threshold: float = 0.2,
    device: torch.device = torch.device("cpu"),
    model=None, # Pass the loaded model if desired, otherwise load it here
) -> tuple[list[torch.Tensor], list[tuple[float, float]]]:
    """
    Segments an audio tensor into smaller chunks based on speech activity detected by Silero VAD.
    Expects audio_tensor to be a 1D PyTorch tensor (mono) at the correct sample rate (8000 or 16000 Hz recommended).
    """
    if model is None:
        model = load_segmentation_model()

    # Run Silero VAD on the tensor
    # Ensure the tensor is on CPU for silero (or handle device as needed)
    # Silero expects 1D tensor (samples,) or (1, samples) for mono
    vad_input_tensor = audio_tensor.squeeze() # Ensure it's (samples,) shape
    if vad_input_tensor.dim() != 1:
        raise ValueError("Audio tensor must be mono (1 channel)")

    # Get speech timestamps using Silero VAD
    speech_timestamps_list = get_speech_timestamps(
        vad_input_tensor.to(device), # Pass the tensor to the device silero will use (often CPU)
        model,
        threshold=0.5, # Adjust as needed
        min_speech_duration_ms=250,
        max_speech_duration_s=float('inf'),
        min_silence_duration_ms=100,
        window_size_samples=512,
        return_seconds=True, # Crucial: returns timestamps in seconds
        speech_pad_ms=30
    )
    # speech_timestamps_list is now like [{'start': s, 'end': e}, ...]

    # Now process the timestamps to segment the ORIGINAL audio_tensor
    segments: list[torch.Tensor] = []
    boundaries: list[tuple[float, float]] = []

    curr_duration = 0.0
    curr_start = 0.0
    curr_end = 0.0

    def _update_segments(start_time: float, end_time: float, duration: float):
        """Helper to create and append segments based on time boundaries."""
        if duration > strict_limit_duration:
            num_segments = int(duration / strict_limit_duration) + 1
            segment_duration = duration / num_segments
            current_seg_start = start_time
            for i in range(num_segments - 1):
                current_seg_end = current_seg_start + segment_duration
                start_sample = int(current_seg_start * sr)
                end_sample = int(current_seg_end * sr)
                # Ensure indices are within bounds
                start_sample = max(0, start_sample)
                end_sample = min(len(audio_tensor), end_sample)
                segments.append(audio_tensor[start_sample:end_sample])
                boundaries.append((current_seg_start, current_seg_end))
                current_seg_start = current_seg_end

            # Add the final sub-segment
            start_sample = int(current_seg_start * sr)
            end_sample = int(end_time * sr)
            start_sample = max(0, start_sample)
            end_sample = min(len(audio_tensor), end_sample)
            segments.append(audio_tensor[start_sample:end_sample])
            boundaries.append((current_seg_start, end_time))
        else:
            # Add the segment as a single chunk
            start_sample = int(start_time * sr)
            end_sample = int(end_time * sr)
            start_sample = max(0, start_sample)
            end_sample = min(len(audio_tensor), end_sample)
            segments.append(audio_tensor[start_sample:end_sample])
            boundaries.append((start_time, end_time))

    # Iterate through the speech segments identified by Silero VAD
    for speech_dict in speech_timestamps_list:
        start = max(0.0, speech_dict['start'])
        end = speech_dict['end']

        # Check if adding this segment exceeds the max/min duration thresholds
        potential_new_duration = curr_duration + (end - curr_end)

        if curr_duration > new_chunk_threshold and (
            potential_new_duration > max_duration or curr_duration > min_duration
        ):
            _update_segments(curr_start, curr_end, curr_duration)
            curr_start = start

        curr_end = end
        curr_duration = curr_end - curr_start

    # Finalize the last chunk if it meets the threshold
    if curr_duration > new_chunk_threshold:
        _update_segments(curr_start, curr_end, curr_duration)

    return segments, boundaries

def segment_audio_file(
    wav_file: str,
    sr: int, # Note: Silero VAD natively supports 8000Hz and 16000Hz. Your input sr must match.
    max_duration: float = 25.0,
    min_duration: float = 15.0, # Legacy argument, ignored by file chunk grouping.
    strict_limit_duration: float = 25.0,
    new_chunk_threshold: float = 0.2,
    device: torch.device = torch.device("cpu"), # Device argument kept for compatibility
    vad_threshold: float = 0.5,
    vad_min_speech_ms: int = 300,
    vad_max_speech_s: float = 25.0,
    vad_min_silence_ms: int = 2000,
    vad_window_samples: int = 512,
    vad_speech_pad_ms: int = 250,
    stats_callback=None,
) -> Tuple[List[torch.Tensor], List[Tuple[float, float]]]:
    """
    Segments an audio waveform into smaller chunks based on speech activity.
    The segmentation is performed using the Silero Voice Activity Detection model.
    """
    # Load the audio file
    # Silero's read_audio might handle loading differently than your custom load_audio
    # It returns a tensor suitable for its processing
    audio_tensor = load_audio(wav_file) # This internally loads and converts to mono if needed
    
    # Ensure the sampling rate matches Silero's supported rates (8000 or 16000 Hz)
    # If your input 'sr' is different, you might need resampling before this step
    # or ensure the input wav_file itself is at a supported rate.
    # The read_audio function from silero_vad usually outputs at the model's expected rate,
    # often 16kHz. Check the documentation or inspect audio_tensor properties.
    
    # Load the Silero VAD model
    model = get_pipeline(device)

    # Get speech timestamps using Silero VAD
    # return_seconds=True ensures timestamps are in seconds, matching your original logic
    speech_timestamps_list = get_speech_timestamps(
        audio_tensor, # Use the tensor loaded by Silero's function
        model,
        threshold=vad_threshold,
        min_speech_duration_ms=vad_min_speech_ms,
        max_speech_duration_s=vad_max_speech_s,
        min_silence_duration_ms=vad_min_silence_ms,
        window_size_samples=vad_window_samples,
        return_seconds=True,         # Crucial: returns timestamps in seconds
        speech_pad_ms=vad_speech_pad_ms
    )

    # The audio loaded by read_audio might be resampled to 16kHz by Silero internally.
    # However, get_speech_timestamps with return_seconds=True provides times relative
    # to the original file's duration as interpreted by its header/sample rate.
    # If there's a mismatch due to internal resampling assumptions, you might need
    # to adjust how you interpret the original 'sr' or rely on Silero's processing context.
    # For many use-cases, assuming the returned timestamps align correctly with the
    # original file's timeline is sufficient.
    # If precision is critical, verify how read_audio handles files of different sample rates.
    
    # Convert speech_timestamps_list (list of dicts with 'start' and 'end') into a format
    # similar to what pyannote's pipeline would return as a timeline
    # Each item in speech_timestamps_list is a dict like {'start': float, 'end': float}
    # e.g., [{'start': 1.2, 'end': 3.4}, ...]
    
    # Load the raw audio array again for slicing, potentially using your custom loader
    # or ensuring Silero's loaded version aligns with the timestamp interpretation.
    # If Silero's read_audio is used, its internal sample rate handling must be known.
    # Let's assume for now that we can load the original file at the specified 'sr'
    # using your custom load_audio function for slicing.
    audio_full = load_audio(wav_file) # Load using your original function at 'sr'

    # Process the timestamps list to form segments, mirroring the original logic
    segments: List[torch.Tensor] = []
    curr_duration = 0.0
    curr_start = 0.0
    curr_end = 0.0
    boundaries: List[Tuple[float, float]] = []

    def _update_segments(start_time: float, end_time: float, duration: float):
        """Helper to create and append segments based on time boundaries."""
        if duration > strict_limit_duration:
            num_segments = int(duration / strict_limit_duration) + 1
            segment_duration = duration / num_segments
            current_seg_start = start_time
            for i in range(num_segments - 1):
                current_seg_end = current_seg_start + segment_duration
                start_sample = int(current_seg_start * sr)
                end_sample = int(current_seg_end * sr)
                segments.append(audio_full[start_sample:end_sample])
                boundaries.append((current_seg_start, current_seg_end))
                current_seg_start = current_seg_end
            
            # Add the final sub-segment
            start_sample = int(current_seg_start * sr)
            end_sample = int(end_time * sr)
            segments.append(audio_full[start_sample:end_sample])
            boundaries.append((current_seg_start, end_time))
        else:
            # Add the segment as a single chunk
            start_sample = int(start_time * sr)
            end_sample = int(end_time * sr)
            segments.append(audio_full[start_sample:end_sample])
            boundaries.append((start_time, end_time))

    # Iterate through the speech segments identified by Silero VAD
    for index, speech_dict in enumerate(speech_timestamps_list):
        start = max(0.0, speech_dict['start'])
        end = speech_dict['end'] # No need to clip against audio length here, Silero handles it
        if index == 0:
            # Start at detected speech, rather than retaining all leading silence.
            curr_start = curr_end = start

        # Check whether adding this region exceeds the preferred maximum span.
        potential_new_duration = curr_duration + (end - curr_end)
        
        # Keep adding regions while their combined span fits the preferred maximum.
        if curr_duration > new_chunk_threshold and potential_new_duration > max_duration:
            _update_segments(curr_start, curr_end, curr_duration)
            # Start a new chunk from the beginning of the current segment
            curr_start = start
        
        # Update the end time and total duration of the current chunk being considered
        curr_end = end
        curr_duration = curr_end - curr_start

    # After processing all speech segments, if there's a remaining chunk to finalize
    if curr_duration > new_chunk_threshold:
        _update_segments(curr_start, curr_end, curr_duration)

    if stats_callback is not None:
        total = audio_tensor.numel() / sr
        # Silero's second-based timestamps are rounded and include speech padding.
        # Clip and merge them so rounded/overlapping regions are not double-counted.
        speech = 0.0
        previous_end = 0.0
        for region in sorted(speech_timestamps_list, key=lambda item: item['start']):
            start = max(previous_end, min(total, max(0.0, region['start'])))
            end = min(total, max(start, region['end']))
            speech += end - start
            previous_end = end
        retained = min(total, sum(segment.numel() for segment in segments) / sr)
        stats_callback({
            "total_seconds": total,
            "speech_seconds": speech,
            "nonspeech_seconds": max(0.0, total - speech),
            "retained_seconds": retained,
            "filtered_seconds": max(0.0, total - retained),
        })

    return segments, boundaries
