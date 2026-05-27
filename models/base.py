from typing import Any, Dict, List, Tuple

class BaseModel:
    @property
    def model_name(self) -> str:
        """The canonical name of the model."""
        raise NotImplementedError

    @property
    def aliases(self) -> List[str]:
        """Alternative names that map to this model."""
        return []

    def get_canonical_name(self, name: str) -> str:
        """Get the specific model name corresponding to the alias used."""
        return self.model_name

    def generate(
        self,
        prompt_json: Dict[str, Any],
        reference_images: List[Dict[str, Any]],
        action: str,
        agent: Dict[str, Any],
        turn_number: int,
        recent_turns: List[Dict[str, Any]],
        assessment: Dict[str, Any],
    ) -> Tuple[str, str, str]:
        """
        Create a generation job/task and block/poll until it is completed.
        Returns:
            Tuple[str, str, str]: (task_id, raw_media_url, prompt_text)
        """
        raise NotImplementedError

    def save_media(
        self,
        raw_media_url: str,
        image_id: str,
        aspect_ratio: str,
    ) -> Dict[str, Any]:
        """
        Download and save media locally.
        Returns:
            Dict[str, Any]: image_webp metadata dictionary.
        """
        raise NotImplementedError

    def get_prompt_guidance_text(self, has_reference_image: bool) -> str:
        """
        Get model-specific guidance to include when drafting prompt instructions.
        """
        return ""

    def get_prompt_rules_text(self, has_reference_image: bool, action: str = "Initiate") -> str:
        """
        Get model-specific rules to include in the rules section of prompt drafting.
        """
        return ""

    def get_prompt_suffix_text(self, has_reference_image: bool) -> str:
        """
        Get model-specific suffix instructions to include after the main rules.
        """
        return ""

    def post_process_prompt_json(self, prompt_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Post-process or clean up the generated prompt JSON for this model.
        """
        return prompt_json

# Global registry of models
MODELS_REGISTRY: Dict[str, BaseModel] = {}

def register_model(model_cls):
    instance = model_cls()
    MODELS_REGISTRY[instance.model_name] = instance
    for alias in instance.aliases:
        MODELS_REGISTRY[alias] = instance
    return model_cls

def get_model(name: str) -> BaseModel:
    model_key = str(name).strip().lower().replace("-", "_").replace(" ", "_")
    if model_key in MODELS_REGISTRY:
        return MODELS_REGISTRY[model_key]
    # Fallback to the default registered model (Runway 'gpt_image_2')
    if "gpt_image_2" in MODELS_REGISTRY:
        return MODELS_REGISTRY["gpt_image_2"]
    raise ValueError(f"Model '{name}' is not registered and no default 'gpt_image_2' fallback was found.")
