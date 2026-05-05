# DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines

**Authors:** Omar Khattab, Arnav Singhvi, Paridhi Maheshwari, Zhiyuan Zhang, Keshav Santhanam, Sri Vardhamanan, Saiful Haq, Ashutosh Sharma, Thomas T. Joshi, Hanna Moazam, et al.
**Venue:** International Conference on Learning Representations (ICLR) 2024
**Year:** 2024
**Bib key:** `khattab2023dspy`
**arXiv:** 2310.03714
**OpenReview:** https://openreview.net/forum?id=sY5N0zY5Od
**Code:** https://github.com/stanfordnlp/dspy

---

## What the paper does

DSPy introduces a **programming model** for LLM pipelines that separates the *structure* of a pipeline from the *parameters* (prompts and few-shot demonstrations). The key abstraction:

- A **DSPy module** is a typed signature: "given these input fields, produce these output fields"
- The module is parameterized: it holds a prompt template and a set of few-shot examples
- A **DSPy compiler** (called an "optimizer") can automatically find prompt/demo parameters that maximize a user-specified metric

Optimizers shipped with DSPy:
- **BootstrapFewShot**: greedy forward pass — runs the module on training examples, keeps traces (input/output) where the metric is high, uses those as demonstrations
- **BootstrapFewShotWithRandomSearch**: runs BootstrapFewShot multiple times with different random seeds, keeps the best configuration
- **MIPROv2**: joint optimization of instructions and demonstrations via Bayesian search (see separate MIPROv2 analysis)

---

## Key contributions

1. **Abstraction**: LLM programs as computational graphs with optimizable parameters, analogous to neural networks
2. **Automatic prompt optimization**: replaces manual prompt engineering with metric-driven search
3. **Reproducibility**: optimized prompts are serializable and reusable; experiments become reproducible
4. **Cross-model transfer**: a prompt optimized for one model can often be applied to another (this paper exploits this via Haiku-optimized demos applied to local SLMs)

---

## Results in the DSPy paper

On several multi-step tasks (question answering, information extraction, reasoning), DSPy-compiled programs outperform:
- Manual few-shot prompting by experienced practitioners
- Chain-of-thought prompting without optimization
- GPT-3.5/4 programs compiled with DSPy compete with or outperform manual GPT-4 chains

Small LMs (T5-770M, Llama-2-13B) with DSPy-compiled prompts are competitive with larger proprietary models using unoptimized prompts.

---

## Relevance to this paper

DSPy is the core optimization infrastructure for the H1 classification task. The paper uses BootstrapFewShot (greedy and with random search) and MIPROv2 across five prompt strategies. The key finding that cross-model demo transfer (Haiku v1 strategy) works as well or better than own-model optimization is a direct observation about DSPy's transfer behavior that isn't covered in the original paper.

DSPy's BootstrapFewShot is what enables the "teacher-student" demo selection strategy described in the paper: Haiku generates high-quality training demonstrations that are then used to prompt weaker local models.
