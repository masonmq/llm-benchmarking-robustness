# Week 4: in-depth code review

This week you will review, in depth, whether the code for three robustness reanalyses does what each reanalysis's plan says it will do.

## Background

- **The study.** We are evaluating robustness reanalyses of published research claims. A robustness reanalysis tests the same claim as the original paper, using the original data but a different, defensible analysis.
- **Each reanalysis has three parts:** a **plan** (the proposed analysis: data, sample, variables, model, test, and a decision rule for whether the result supports the claim), the **code** that implements the plan, and the **output** recorded when that code was run, ending in a conclusion: *support*, *borderline*, *inconclusive* or *opposite*.
- **Task 1 and Task 2.** Each reanalysis was done under one of two tasks. In **Task 1** there was no restriction: any defensible analysis of the claim could be chosen. In **Task 2** the analysis had to follow a specific restriction.
- **Labels.** Analyses are labeled by letter and task, for example *Analysis A — Task 2*. The letters do not indicate order or quality.

## This week's paper and claim

**Paper:** Bruner (2017), "Does decision error decrease with risk aversion?", *Experimental Economics*.

**The claim all three analyses test:**

> More importantly, violations are consistent with stochastic decision error that decreases with risk aversion.

**Task 2 restriction** (applies to Analysis A — Task 2): *You should not use rank-order tests in your analysis.*

## Your task this week

You will review **three analyses** of this claim. For each one, your question is: **does the code faithfully implement the plan?**

- You are **not** judging whether the plan itself is a good analysis. Take the plan as given and check whether the code does what the plan says.
- A difference between plan and code can matter even if it does not change the result here; Step 6 asks you to judge that separately.
- Code style, efficiency and comments do not matter.

**Time:** about 20–30 minutes to read the paper, then about **60 minutes per analysis**, so about **2.5–3 hours in total**. You do not need to finish in one sitting.

**Deadline:** Wednesday, November 4, 2026.

## Your materials

In the **Week 4** subfolder of your Google Drive folder for this project you will find:

- `original_paper.pdf`: the paper.
- `RiskData.dta` and `data_README.txt`: the data the analyses use, and its documentation.
- Three notebooks, one per analysis: `Bruner_Analysis_A_-_Task_2.ipynb`, `Bruner_Analysis_C_-_Task_1.ipynb`, `Bruner_Analysis_E_-_Task_1.ipynb`.

Each notebook shows the claim, the plan and the code, and guides you through the review.

## Getting started in Google Colab

1. **Open each notebook from your Week 4 folder in Google Drive:** right-click the notebook → **Open with → Google Colaboratory**. (If Colab is not listed, choose *Connect more apps*, search for "Colaboratory" and install it.) Please do **not** use Colab's *Upload notebook* option: that makes a separate copy, and we would not receive your answers.
2. Run the three **Setup** cells at the top. The second one asks you to upload `RiskData.dta` from your Week 4 folder.
3. Work through the four parts in the notebook. Nothing needs to be installed.

**Whenever you come back to a notebook,** run the three Setup cells again. Colab forgets uploaded files when it disconnects, but everything you typed is kept.

## The four parts

Each notebook walks you through the same four parts (about 60 minutes in total):

| Part | About | What you do |
|---|---|---|
| 1. Run the code | 10 min | Run the analysis and check that its output matches the recorded output shown in the notebook. |
| 2. Map the plan to the code | 30 min | The plan is split into items, in the plan's own words. For each item, write the line number(s) of the code that implement it, judge whether those lines are a valid implementation (*Valid*, *Partly*, *Not valid*, *Not implemented* or *Can't tell*), and add a short note unless it is *Valid*. |
| 3. Code the plan does not mention | 5 min | List anything the code does that the plan does not state (for example an extra filter, a different test, or a hard-coded value) and whether it matters. |
| 4. Severity and rating | 10 min | For each problem you found, would it change this analysis's conclusion? Then give an overall 1–5 rating. |

`show_code()` prints the code with line numbers, so you can refer to lines easily.

**Explore and test.** You are encouraged to look at the data and to try out any lines you are unsure about. The notebook has a scratch cell that loads the data as `df`; copy the lines you question into it and check the result, for example how many rows remain after a filter, or a few values of a constructed variable. Do **not** edit the cell that contains the analysis code itself.

## Recording your answers

Everything happens inside the notebooks; there are no separate forms.

- **In each part,** run the part's **start** cell when you begin (it records the time for us), then type your answers into the **answer cell** (choose from the options shown in the comments) and run it.
- **At the end of each notebook,** run `finish()`. It tells you if any answer is missing.
- **Feedback:** in whichever notebook you finish last, fill in the short **Feedback** section (once only).

If an analysis takes much longer than 90 minutes, stop, note where you stopped in the last answer cell, and move on.

## Saving: please read

Your answers reach us **only** through the notebooks saved in your Week 4 folder.

- Save often: **File → Save** (or Ctrl/Cmd+S). Check that the top of the page says *All changes saved*.
- Before closing a notebook, save once more and confirm *All changes saved*.
- Do **not** clear the cell outputs (the start and finish cells' printed times are part of what we collect).
- If Colab ever says you are working in a copy or in "playground mode", you opened the notebook the wrong way: go back to your Drive folder and open it with *Open with → Google Colaboratory*.

## Ground rules

- Please do not use ChatGPT or any other AI tool to review the code.
- Do not discuss the analyses with other reviewers until after the deadline.

Questions: {{CONTACT}}.
