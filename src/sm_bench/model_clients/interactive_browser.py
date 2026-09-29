from sm_bench.model_clients.base import BaseModelClient

class InteractiveBrowserClient(BaseModelClient):
    def __init__(self):
        super().__init__("InteractiveBrowserClient")

    def generate_design(self, prompt: str) -> str:
        print("\n" + "="*50)
        print("SYSTEM AND USER PROMPT:")
        print("="*50)
        print(prompt)
        print("="*50)
        print("\nCopy the prompt above, paste it into ChatGPT/Claude/Gemini in your browser.")
        print("Then, paste the model's response below.")
        print("Enter 'END' on a new line to finish your input.\n")
        
        lines = []
        while True:
            try:
                line = input()
                if line.strip() == "END":
                    break
                lines.append(line)
            except EOFError:
                break
                
        return "\n".join(lines)
