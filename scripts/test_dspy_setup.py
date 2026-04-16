"""
test_dspy_setup.py — Verify DSPy environment before running the full evaluation

Runs a single example through the ExtraContentClassifier signature using whichever
provider you specify. Takes ~5 seconds and costs <$0.001. If it prints a classification
and reasoning, your environment is configured correctly.

Usage:
    # Test Anthropic (Haiku):
    python test_dspy_setup.py --provider anthropic --model claude-haiku-4-5-20251001

    # Test Together AI (Mistral-7B):
    python test_dspy_setup.py --provider together --model mistralai/Mistral-7B-Instruct-v0.2

    # Test Groq (Llama-3.1-8B, free):
    python test_dspy_setup.py --provider groq --model llama-3.1-8b-instant

    # Test Ollama (local, requires: brew install ollama + ollama pull mistral + ollama serve):
    python test_dspy_setup.py --provider ollama --model mistral

    # Test Ollama with Llama:
    python test_dspy_setup.py --provider ollama --model llama3.1

    # Test the optimized saved program instead of zero-shot:
    python test_dspy_setup.py --provider ollama --model mistral --load-path optimized/h1_haiku.json

Troubleshooting:
    Anthropic:   Set ANTHROPIC_API_KEY in .env
    Together AI: Set TOGETHER_API_KEY in .env (get key at https://api.together.xyz/settings/api-keys)
    Groq:        Set GROQ_API_KEY in .env (get key at https://console.groq.com)
    Ollama:      Must have server running. On Mac:
                   Option A — install desktop app from https://ollama.com (recommended)
                   Option B — run `ollama serve` in a separate terminal
                 Then pull the model:  ollama pull mistral
                 Check it's running:   curl http://localhost:11434/api/tags
"""

import argparse
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

try:
    import dspy
except ImportError:
    sys.exit("dspy-ai not installed. Run: pip install dspy-ai")

VALID_CLASSES = {"business_type", "location", "disambiguation", "noise"}

class ExtraContentClassifier(dspy.Signature):
    """
    Classify the semantic role of extra content in a place name subset conflict.

    Context: One place name is entirely contained within another. The longer name adds
    "extra content" beyond the shorter core name. Your job is to classify what that
    extra content IS — this determines whether to keep the longer or shorter name.

    Four classes:
    - business_type: The extra content describes what KIND of place this is (Hotel,
      Supermarket, Dance Studio, Dental Clinic, Pharmacy, Florists, Ice Arena).
      → Select the LONGER name.
    - location: The extra content is a place name — city, neighborhood, state, country.
      Examples: Champs-Elysées, Florida, Hammersmith, Canada, Marseille, Azcapotzalco.
      → Select the SHORTER name.
    - disambiguation: Branch, owner, affiliation, or service list — not a place or type.
      Examples: State Farm Insurance Agent, Coldwell Banker Commercial, Franchisé indépendant.
      → Select the SHORTER name.
    - noise: Listing boilerplate — licence numbers, credentials, legal suffixes, taglines.
      Examples: NMLS #344084, M.D., e.K., Uno dei Borghi più Belli d'Italia, Limited.
      → Select the SHORTER name.
    """
    short_name:    str = dspy.InputField(desc="The shorter, core place name")
    long_name:     str = dspy.InputField(desc="The longer place name containing the extra content")
    extra_content: str = dspy.InputField(desc="The extra content (lowercased, punctuation stripped)")
    script_type:   str = dspy.InputField(desc="Script family: latin, cjk, or thai")
    classification: str = dspy.OutputField(desc="One of exactly: business_type, location, disambiguation, noise")
    confidence:     str = dspy.OutputField(desc="One of exactly: high, medium, low")
    reasoning:      str = dspy.OutputField(desc="One sentence explaining the decision")


class ExtraContentModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.classify = dspy.ChainOfThought(ExtraContentClassifier)

    def forward(self, short_name, long_name, extra_content, script_type):
        pred = self.classify(short_name=short_name, long_name=long_name,
                             extra_content=extra_content, script_type=script_type)
        cls = pred.classification.strip().lower().replace(" ","_").replace("-","_")
        if cls not in VALID_CLASSES:
            for v in VALID_CLASSES:
                if v in cls: cls = v; break
            else: cls = "disambiguation"
        pred.classification = cls
        return pred


def configure_lm(provider, model):
    if provider == "anthropic":
        lm = dspy.LM(f"anthropic/{model}")
    elif provider == "openai":
        lm = dspy.LM(f"openai/{model}")
    elif provider == "ollama":
        lm = dspy.LM(f"ollama_chat/{model}", api_base="http://localhost:11434")
    elif provider == "together":
        lm = dspy.LM(f"together_ai/{model}")
    elif provider == "groq":
        lm = dspy.LM(f"groq/{model}")
    else:
        lm = dspy.LM(model)
    dspy.configure(lm=lm)

# ── Two test cases — one clear, one harder ────────────────────────────────────

TEST_CASES = [
    {
        "short_name":    "Les Hospitaliers",
        "long_name":     "Les Hospitaliers Hotel",
        "extra_content": "hotel",
        "script_type":   "latin",
        "expected":      "business_type",
        "note":          "Clear business type — hotel describes what the place IS",
    },
    {
        "short_name":    "Kip McGrath",
        "long_name":     "Kip McGrath Hammersmith",
        "extra_content": "hammersmith",
        "script_type":   "latin",
        "expected":      "location",
        "note":          "Geographic location — Hammersmith is a London neighbourhood",
    },
    {
        "short_name":    "George McFaden",
        "long_name":     "George McFaden at Guaranteed Rate Affinity - NMLS #344084",
        "extra_content": "at guaranteed rate affinity nmls 344084",
        "script_type":   "latin",
        "expected":      "noise",
        "note":          "NMLS licence number — listing boilerplate",
    },
]


def main():
    parser = argparse.ArgumentParser(description="Smoke test for DSPy setup")
    parser.add_argument("--provider",   default="ollama",    help="LM provider")
    parser.add_argument("--model",      default="mistral",   help="Model name")
    parser.add_argument("--load-path",  default=None,        help="Load optimized program")
    args = parser.parse_args()

    print(f"Testing DSPy setup — provider={args.provider}  model={args.model}")
    print()

    # Check Ollama server if relevant
    if args.provider == "ollama":
        import urllib.request, urllib.error
        try:
            with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
                import json
                data = json.loads(r.read())
                models = [m['name'] for m in data.get('models', [])]
                print(f"Ollama server: running  |  available models: {models}")
                if not any(args.model in m for m in models):
                    print(f"\nWARNING: '{args.model}' not found in Ollama models.")
                    print(f"Run:  ollama pull {args.model}")
                    sys.exit(1)
        except urllib.error.URLError:
            print("ERROR: Ollama server is not running.")
            print()
            print("Fix:")
            print("  Option A (recommended): Open the Ollama desktop app from Applications")
            print("  Option B: Run `ollama serve` in a terminal and keep it open")
            print()
            print("Then re-run this script.")
            sys.exit(1)
        print()

    try:
        configure_lm(args.provider, args.model)
    except Exception as e:
        print(f"ERROR configuring LM: {e}")
        sys.exit(1)

    module = ExtraContentModule()
    if args.load_path:
        module.load(args.load_path)
        print(f"Loaded optimized program from: {args.load_path}")
        print()

    passed = 0
    for i, tc in enumerate(TEST_CASES, 1):
        print(f"Test {i}: {tc['note']}")
        print(f"  short:  {tc['short_name']}")
        print(f"  long:   {tc['long_name']}")
        print(f"  extra:  {tc['extra_content']}")
        try:
            pred = module(
                short_name=tc['short_name'],
                long_name=tc['long_name'],
                extra_content=tc['extra_content'],
                script_type=tc['script_type'],
            )
            match = "PASS" if pred.classification == tc['expected'] else "FAIL"
            if pred.classification == tc['expected']:
                passed += 1
            print(f"  result: [{match}]  predicted={pred.classification}  expected={tc['expected']}")
            print(f"  confidence: {getattr(pred, 'confidence', 'n/a')}")
            print(f"  reasoning: {getattr(pred, 'reasoning', 'n/a')}")
        except Exception as e:
            print(f"  result: [ERROR]  {e}")
        print()

    print(f"{'='*50}")
    print(f"Result: {passed}/{len(TEST_CASES)} tests passed")
    if passed == len(TEST_CASES):
        print("Environment is configured correctly.")
        print(f"Ready to run: python 11_dspy_extra_content.py --provider {args.provider} --model {args.model}")
    elif passed > 0:
        print("Partial pass — model is working but may need optimization.")
        print(f"Try running with the optimized prompt: --load-path optimized/h1_haiku.json")
    else:
        print("All tests failed. Check your API key and model name.")


if __name__ == "__main__":
    main()
