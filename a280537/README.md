# A280537: a new lower bound a(28) ≥ 58 (no four points in a plane)

> This folder is part of [Challenging Real-World Problems](https://github.com/parkseyoung1215-netizen/challenging-real-world-problems), where I take on real problems with AI. Other projects there: a world simulator (what-if-world) and a furniture planner (say-and-build).

**My decision.**
I started this project because I wanted to become someone who solves hard or unsolved problems with AI. For my first attempt I tried the no-three-in-line problem, but even after trying many different cases and methods I did not succeed. So I decided to switch to a different problem from the list of problems I had set out at the beginning, and I chose this one. When the result came out, I cross-checked it again on my own MacBook to confirm it.

What I took away from this challenge is that I should keep trying to use AI to work on the world’s problems that are still not fully solved. AI is a useful enough tool to make these attempts possible, and I think it should be used efficiently.

**Problem.** [OEIS A280537](https://oeis.org/A280537): the maximum number of points that can be chosen from an n × n × n grid with no four of them in a plane.

**Result.** `a280537_n28_58.txt` gives 58 points in the 28 × 28 × 28 grid {0..27}³, no four of them coplanar. So **a(28) ≥ 58**.

**Archived:** Zenodo, https://doi.org/10.5281/zenodo.23700817

**Previous best known.** Al Zimmermann's 2016 contest "Non-Coplanar Points" reports 66 points for n = 29. Any plane x = const can hold at most 3 points, so removing the three outer layers x = 28, y = 28 and z = 28 from a 66-point configuration removes at most 9 points and leaves at least 57 points in the 28 × 28 × 28 grid. So a(28) ≥ 57 follows from the n = 29 result. The contest configurations are not public, so 57 is the best bound that can be derived from published values. 58 improves it by one.

- The OEIS entry lists terms and lower bounds only up to n = 18.
- Al Zimmermann's contest results: https://azspcs.com/Contest/Tetrahedra/FinalReport

**Correction (2026-10-17).** I first wrote that my 57-point configuration (`a280537_n28_57.txt`) was a new lower bound, because I thought the previous best for n = 28 was 56. That was wrong: a(28) ≥ 57 already follows from the n = 29 result, as explained above. The 57-point file is kept for the record.

**OEIS (2026-10-28).** I proposed this bound for A280537. The editors decided not to add results for n > 18 to the entry while the exact terms for n > 8 are still unknown, so the link was not included. The submission and discussion are in the [A280537 edit history](https://oeis.org/history?seq=A280537).

## Verification
1. `verify4.py`: for every 4-subset of the points, the integer determinant det(b−a, c−a, d−a) is nonzero.
```
   python3 verify4.py a280537_n28_58.txt
```
2. The 58-point configuration (found 184 s into an 8-hour run on 2026-10-18) was checked with `verify4.py` on the author's own MacBook Air: `OK n28.txt n=28: 58 points, no four coplanar`.
3. The earlier 57-point configuration was checked the same way on 2026-10-17 (`OK a280537_n28_57.txt n=28: 57 points, no four coplanar`), and also by a second, plane-hashing check: all C(57,3) = 29,260 triples span 29,260 distinct planes, so no plane contains four of the points.

## How it was found
`search5.c` uses min-conflicts tabu local search for a fixed number of points K. Each grid cell keeps a count of how many lines (through pairs of chosen points) and planes (through triples of chosen points) pass through it. Adding a cell with count 0 keeps the set valid. Starting from a greedy valid set, the search repeatedly swaps the most-conflicted chosen point for the least-conflicted free cell. When it reaches zero conflicts it records the set and tries K+1.

The search code was written and run with an AI assistant (Claude) as part of this project.

```
gcc -O3 -o search5 search5.c
./search5 28 28800 2 out.txt      # n, seconds, random seed, output file
python3 verify4.py out.txt
```

## Other attempts (10-minute runs, same program)
| n | found | best known |
|---|---|---|
| 20 | 43 | 46 |
| 24 | 50 | 54 |
| 25 | 52 | 54 |
| 26 | 54 (also 54 in 8 h) | 54 |
| 30 | 61 | 66 |
