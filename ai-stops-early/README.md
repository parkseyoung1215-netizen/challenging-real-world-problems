# Why AI Stops Early

Can an AI solve hard problems better if it does not believe they are impossible?
Six experiments with OpenAI models (mostly gpt-5-mini, about 1,400 API calls) say no:
the belief does not matter. What makes the model fail is that it **settles for a
plausible answer** and stops checking it, even when the evidence against it is in front of it.

Every correct answer was computed directly by brute force (up to 10^9 for the large
problems, with a C program), never taken from a model.

## Results at a glance

| # | Question | Result |
|---|----------|--------|
| 1, 2 | Does framing change accuracy? ("unsolved problem" / "already-solved homework" / nothing / "verify each step") | No. In run 2 (375 problems, gpt-5-mini) every framing scored 80 to 85%, p = 0.66 to 1.00 vs. no framing |
| 3 | If it is not belief, why does it fail? Does checking help? (range 10^4) | Pattern problems fail the same way every time (S1: 9841 five out of five times). Majority vote locks the error in, self-recheck fixes 1 of 15. Code that counts everything: 40/40 |
| 4 | Same problems, range 10^9 (counting everything is impossible) | Every method 0/32. The code built the same wrong pattern in (L1: 7 of 8 programs printed 581130733, the "powers of 3 only" value). Reasoning and code agreed 14 times, all 14 wrong |
| 5 | Catch the wrong code with independent checks, then let the model fix it | Checks caught 51 of 55 wrong programs, 0 false alarms. Fixes: 3/24 before, 3/24 after |
| 6 | Also show the full list of true answers up to 10^6 | Data + checks: 8/24 correct, vs. 3/56 without data (p = 0.002). But the model wrote rules that the given list itself contradicts |

### The clearest case (run 6)

Both repeated wrong answers for L1 came from rules of the form "n = 3^k × m, and every
prime of m divides 2^(3^k) + 1". The true answer 97641 = 3² × 19 × 571 breaks this:
571 divides 2^(3·19) + 1, not 2^(3^k) + 1 (the order of 2 mod 571 is 114 = 2 × 3 × 19).
**97641 was in the list given to the model.** One of the rules fails to explain 12 of the
40 listed numbers, the other 3, and the model never compared its rule with the list.

### The "187" case (run 4)

One program used the right structure and found 187 of the 188 answers. It missed
751611177 = 3³ × 19 × 1465129 because it only listed primes up to 10^6, with the comment
`# 1e6: sufficiently large`. With a larger prime bound the same program prints 188.

## How it relates to existing work

Already known: LLMs rarely fix reasoning errors without outside feedback; majority
voting reinforces shared wrong answers
([Consensus is Not Verification](https://arxiv.org/html/2603.06612),
[When Self-Consistency Backfires](https://arxiv.org/html/2608.11403v1)); models silently
omit members when listing a set
([Judging Is Not Enumerating](https://arxiv.org/html/2608.01000)); a model hard-coding
too small a search bound was noted as one case in
[MathArena's Project Euler analysis](https://matharena.ai/euler/).

Not found in our search: the same problem flipping from 100% to 0% under code
verification when only the range grows; predicting a model's wrong answer in advance from
the "strong law of small numbers" (S2 was built to miss 5050, and did, 5 of 5 times); a
model ignoring a counterexample inside the data it was given. This is one model and a
small set of problems, so these are observations, not established findings.

## Files

| Path | What |
|------|------|
| `experiments/run_experiment.py` | Run 1: four framings, gpt-5 / gpt-4o-mini / gpt-5-mini |
| `experiments/run_experiment2.py`, `analyze2.py` | Run 2: harder problems, five framings, reasoning tokens |
| `experiments/run_experiment3.py` | Run 3: five checking methods, range 10^4 |
| `experiments/run_experiment4.py` | Run 4: range 10^9 |
| `experiments/run_experiment5.py`, `regrade5.py` | Run 5: independent checks + rewrite (`regrade5.py` counts timeouts as failures) |
| `experiments/run_experiment6.py` | Run 6: true answer list up to 10^6 given, checks at 10^7 |
| `results/` | Every model reply and its grading (`results*.csv`), summaries, the rules the model stated in run 6 (`rules6_gpt-5-mini.txt`) |

To rerun: `export OPENAI_API_KEY=...`, then `python3 experiments/run_experiment6.py`
(or any other run). Runs 3 to 6 execute model-written Python locally, skipping code that
touches files, the network or other programs.

## Next

Run 7: make the model regenerate the given list from its own rule and show it exactly
which numbers are missing, before it computes the large answer. See [devlog](devlog.md).
