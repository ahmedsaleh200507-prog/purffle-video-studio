"""Download/verify the free local model before spending time on a batch."""
import os
from transformers import CLIPModel, CLIPProcessor

if __name__ == '__main__':
    model = os.environ.get('PURFFLE_CLIP_MODEL', 'openai/clip-vit-base-patch32')
    CLIPProcessor.from_pretrained(model)
    CLIPModel.from_pretrained(model)
    print('Local CLIP weights loaded successfully; no paid inference API used', flush=True)
