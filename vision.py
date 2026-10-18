"""
AccessAI - AI Image Recognition (Member 4)
Uses zero-shot image classification (CLIP) to identify stairs, ramps, obstacles,
and clear footpaths. Loads lazily on demand without blocking server startup.
"""

import os

LABELS = [
    'a staircase',
    'a wheelchair ramp',
    'a blocked footpath with an obstacle',
    'a smooth clear footpath',
]

_classifier = None
_classifier_attempted = False
_classifier_error = None


def get_classifier():
    """Lazily loads the CLIP zero-shot classification pipeline on first request."""
    global _classifier, _classifier_attempted, _classifier_error
    if _classifier is not None:
        return _classifier, None

    if _classifier_attempted and _classifier_error:
        return None, _classifier_error

    _classifier_attempted = True
    try:
        import importlib
        pipeline_module = importlib.import_module('transformers')
        pipeline_fn = getattr(pipeline_module, 'pipeline')
        # Load CLIP model on demand (will use cached weights if available)
        _classifier = pipeline_fn(
            'zero-shot-image-classification',
            model='openai/clip-vit-base-patch32'
        )
        return _classifier, None
    except ImportError:
        _classifier_error = "Missing dependencies: 'transformers' or 'torch' are not installed in the environment."
        return None, _classifier_error
    except Exception as e:
        _classifier_error = f"Model loading failed: {str(e)}"
        return None, _classifier_error


def is_ai_available():
    """Checks if the required libraries are installed."""
    import importlib.util
    return (
        importlib.util.find_spec('transformers') is not None
        and importlib.util.find_spec('torch') is not None
    )


def analyze(path):
    """
    Classifies a photo into accessibility categories.
    Returns:
        tuple (label, confidence_score) or raises RuntimeError if model unavailable.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Image not found at path: {path}")

    clf, err = get_classifier()
    if clf is None:
        # Honest message instead of fabrication or crashing
        raise RuntimeError(
            f"AI classification unavailable. {err} "
            f"Please run 'pip install transformers torch' and download the CLIP model weights to enable live inference."
        )

    results = clf(path, candidate_labels=LABELS)
    best = results[0]
    return best['label'], round(float(best['score']), 2)


if __name__ == '__main__':
    import glob
    print("Testing vision module on photos...")
    photos = glob.glob('photos/*.jpg') + glob.glob('photos/*.png')
    if not photos:
        print("No photos found in photos/ directory.")
    for p in photos:
        try:
            label, score = analyze(p)
            print(f"{p}: {label} ({score * 100:.1f}%)")
        except Exception as ex:
            print(f"{p}: Error - {ex}")
