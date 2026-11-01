# smartdevtool/wrapper/inputs/universal_input.py
from smartdevtool.llm.client import LLMClient
from smartdevtool.wrapper.inputs.curl_input import CurlInput
from smartdevtool.wrapper.inputs.doc_input import DocInput
from smartdevtool.wrapper.inputs.har_input import HarInput
from smartdevtool.wrapper.inputs.postman_input import PostmanInput


class UniversalInput:
    def __init__(self, raw_input: str):
        self.raw_input = raw_input.strip()
        self.llm = LLMClient()

    def detect_type(self) -> str:
        """Detect input type based on content/extension."""
        if self.raw_input.lower().startswith("curl "):
            return "curl"
        if self.raw_input.lower().endswith(".har"):
            return "har"
        if self.raw_input.lower().endswith(".json") and "postman" in self.raw_input.lower():
            return "postman"
        if self.raw_input.startswith("http://") or self.raw_input.startswith("https://"):
            return "doc"
        return "prompt"

    def parse(self):
        """Route input to correct parser or escalate to LLM."""
        input_type = self.detect_type()

        if input_type == "curl":
            return CurlInput(self.raw_input).parse()
        elif input_type == "doc":
            return DocInput(self.raw_input).parse()
        elif input_type == "postman":
            return PostmanInput(self.raw_input).parse()
        elif input_type == "har":
            return HarInput(self.raw_input).parse()
        else:
            # Free-form prompt or website name - escalate to LLM
            return self.llm.extract_endpoints(self.raw_input)
