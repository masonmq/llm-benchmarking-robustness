# Week {{WEEK}} instructions: reviewing robustness analyses (code reviewer)

Thank you for taking part in this evaluation. You will review statistical reanalyses that were proposed and implemented to test a claim from a published paper.

**This is a weekly task: we expect you to complete one paper per week.** This document covers your paper for week {{WEEK}}. Instructions for any later papers will be placed in the same Google Drive folder that was shared with you for this document, so please use that folder to access your subsequent papers. Each paper has its own one-week deadline.

## Access

- Evaluation link: [**{{PAPER_LINK}}**]({{PAPER_LINK}})
- Assigned username: **{{USERNAME}}**
- Study password: sent separately
- Please complete this paper by: **{{DEADLINE}}** (one week after you receive this link)
- Contact for questions or technical problems: **{{CONTACT}}**

Please always use your assigned username. Your responses and saved progress are linked to it. Do not share your username.

## Timeline and commitment

- **One paper at a time.** Your assigned papers will be sent one at a time over the next few weeks, never more than one per week. Each paper has a one-week turnaround: please complete it by the date above.
- **Time per paper:** we expect about **2–2.5 hours** per paper, depending on the paper. You do not need to finish in one sitting.
- **Expectations and authorship:** these are described in the email that accompanied this document.
- **If your availability changes,** or you cannot complete a paper within its week, please let us know at **{{CONTACT}}** as early as possible so we can reassign it.

## Before you begin

- Use a laptop or desktop browser rather than a phone.
- Complete the evaluation independently.
- **Do not use ChatGPT or any other AI tool to evaluate the proposed analysis, code, results, or conclusion.**
- You may consult the original paper, data, and documentation provided in the application at any point during the review.
- Please do not redistribute the study materials or the evaluation link.

The form saves your responses automatically. Check that the status at the top says **Saved** before you close the page. You do not need to finish in one sitting: you can close the browser and resume later by signing in with the same username. Please do not have the same paper open in more than one browser tab at a time.

**Submitting a part is final.** When you select **Submit Part N**, the answers in that part are locked and cannot be changed. The next part is revealed only after you submit the current one.

## What you will review

Each paper has **up to 10 analyses** of one focal claim: 5 independent analyses (A–E), each with 2 tasks. When an analysis's Task 1 and Task 2 produced exactly the same result, only the Task 2 analysis is shown, so some papers have fewer than 10. The first analysis usually takes longest, while you become familiar with the paper.

- **Analyses are independent.** The letters do not indicate order or quality. Review each analysis on its own merits, and do not assume one is correct because another uses a similar method.
- **Task 1 has no restriction.** Any defensible analysis of the claim could be chosen.
- **Task 2 has a restriction.** The analysis was required to follow a specific restriction, such as using a particular dataset, measure, or set of controls. The restriction is shown in Parts 2 and 3 of every Task 2 analysis.

## The review parts

Part 1 is completed once for the paper. Parts 2–4 are completed for each analysis.

### Part 1: Review the source material (once per paper)

Get familiar with the focal claim, paper, data, and documentation. You do not need to read the entire paper or inspect every data file before continuing. At a minimum, review enough to understand:

- the focal claim;
- the relevant study and population;
- the main outcome, predictor, and other important variables; and
- the general structure of the available data.

The abstract or introduction, the relevant study description, and variable names or labels are often a sufficient starting point. You can return to these materials at any time when a later judgment requires more detail.

The files are grouped to help you focus:

- **Files labeled "Used in the proposed analyses"** are the datasets the analysis code loads. Start with these.
- **Documentation** (such as a README or codebook) is listed next.
- **Other files in the reproduction package** are collapsed and optional. They include other data files and, for some papers, the original authors' code. You do not need to review them, but you may consult them if useful.

### Part 2: Review the proposed analysis

Assess whether the proposed analysis tests the focal claim and whether the method is defensible. The displayed analysis choices, claim mapping, and source justifications were written as part of the proposal. Pay particular attention to the proposed:

- population and sample restrictions;
- outcome, predictor, moderator, and variable construction;
- statistical model and focal comparison;
- missing-data and outlier handling; and
- expected direction and decision rule.

**For Task 2 analyses**, you will also judge whether the proposed analysis follows the Task 2 restriction.

Select the best answer for each question and give the required explanation. Each Part 2 question is answered Yes, No, Unclear, or Insufficient information. Choose **Unclear** when you have what you need but the call is borderline, and **Insufficient information** when something you need is missing from the materials.

### Part 3: Review the implementation

Open the analysis code (Python) and compare it with the analysis proposed in Part 2. Consider whether the code uses the planned data, variables, sample and exclusions, transformations, model, and statistical test. **For Task 2 analyses**, also check that the code correctly follows the Task 2 restriction.

What we are asking is whether the code does what the plan says. You do not need to verify every line of syntax. If you cannot verify part of the code, say so in your explanation.

**Running the code is optional.** The application cannot run code. If it helps your review, you can download the code and data files from the viewer and run them yourself. This is not required.

If you choose to run it:

- **Where to run it:** [Google Colab](https://colab.research.google.com) runs Python in your browser with nothing to install; upload the code file and the data file. Locally, [VS Code](https://code.visualstudio.com) with the Python extension or [Jupyter](https://jupyter.org) both work.
- **Where to put the data:** the code looks for its data file in a folder named `data` next to where the code runs. Place the downloaded data file(s) in that folder.
- **Packages:** install the packages listed in the `import` lines at the top of the file (for example, `pip install pandas numpy scipy`). SPSS (`.sav`) data files also need `pyreadstat`.
- **Expected output:** the printed output should match the recorded analysis output shown in Part 4.

For the 1–5 implementation-fidelity rating:

1. The implementation does not follow the proposed analysis.
2. It follows the proposal only weakly and has important discrepancies.
3. It follows the proposal in some respects but has meaningful ambiguities or discrepancies.
4. It follows the proposal closely, with only minor discrepancies.
5. It faithfully implements the proposed analysis.

Explain the evidence supporting your rating, including any discrepancies you found.

### Part 4: Review the analysis results and conclusion

First inspect the **recorded analysis output**, which was captured when the code ran. Then compare it with the reported result and conclusion. The report may select and interpret only some of the values in the full output. The application may display a **Potential result mismatch** warning when a number in the report cannot be found in the recorded output. Treat this as a prompt for closer review, not as proof that the analysis is invalid.

The reported **claim classification** says whether the focal claim is considered supported, opposed, or inconclusive. **Your rating is a different judgment: whether that interpretation is justified by the recorded results.**

For the 1–5 conclusion-justification rating:

1. **Not justified**: the conclusion conflicts with or misrepresents the results.
2. **Weakly justified**: major problems affect the interpretation.
3. **Partially justified**: the interpretation is mixed, ambiguous, or incomplete.
4. **Well justified**: the interpretation is mostly appropriate, with minor reservations.
5. **Fully justified**: the conclusion accurately follows from the relevant results.

Consider the effect estimate, direction, uncertainty interval, statistical test, sample size, and the stated decision rule. Explain the evidence supporting your rating. **Use the final optional comment box for important issues not covered by the preceding questions.**

## If something goes wrong

If a file does not open, the code shows as **Code is not available**, the status does not say **Saved**, or you cannot sign in, please contact **{{CONTACT}}** before continuing with that analysis.
