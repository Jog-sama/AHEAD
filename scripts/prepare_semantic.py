"""Optional ADE20K semantic floor checkpoint download (requires internet).

Run in .venv-obstacle: python -m scripts.prepare_semantic
This opt-in model is not needed for native ARKit LiDAR mode.
"""

from pathlib import Path


def main():
    from transformers import AutoImageProcessor, AutoModelForSemanticSegmentation
    name = "nvidia/segformer-b0-finetuned-ade-512-512"
    target = Path("models/segformer-ade20k-b0")
    target.mkdir(parents=True, exist_ok=True)
    processor = AutoImageProcessor.from_pretrained(name)
    model = AutoModelForSemanticSegmentation.from_pretrained(name)
    processor.save_pretrained(target)
    model.save_pretrained(target)
    print(f"Saved optional RGB floor segmentation model in {target}")


if __name__ == "__main__":
    main()
