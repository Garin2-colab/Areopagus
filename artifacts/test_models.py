import sys
import os

# Add current workspace to path
sys.path.insert(0, r"c:\Users\heebo\Documents\Vibecoding Projects\Areopagus")

from models import get_model

model = get_model("midjourney")
print("Resolved class:", model.__class__.__name__)

prompt_json = {
    "scene_description": "a majestic courtroom with a massive tribunal",
    "subject": "justice statue, nick knight style",
    "ratio": "16:9"
}
refs = [{"uri": "https://example.com/parent-ref.jpg", "tag": "ReferenceImage"}]

agent = {
    "prompt_image": "https://example.com/profile-style.jpg",
    "referenceImages": ["https://example.com/uploaded-style1.jpg", "https://example.com/uploaded-style2.jpg"]
}

initiate_prompt = model.format_midjourney_prompt(prompt_json, refs, "Initiate", agent=agent)
print("Initiate prompt format:")
print(f"  {initiate_prompt}")

pivot_prompt = model.format_midjourney_prompt(prompt_json, refs, "Pivot", agent=agent)
print("Pivot prompt format:")
print(f"  {pivot_prompt}")
