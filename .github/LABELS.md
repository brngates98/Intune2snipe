# GitHub labels (one-time setup)

Issue templates apply these labels: **BUG**, **TODO**, **ENHANCEMENT**, **FEATURE REQUEST**.

GitHub does not create labels from git alone. Create them once in the repo (UI: **Issues → Labels**), or with [GitHub CLI](https://cli.github.com/) from the repository root:

```bash
gh label create "BUG" --color "d73a4a" --description "Defect or incorrect behavior"
gh label create "TODO" --color "cfd3d7" --description "Actionable task or follow-up"
gh label create "ENHANCEMENT" --color "a2eeef" --description "Improvement to existing behavior or DX"
gh label create "FEATURE REQUEST" --color "0075ca" --description "New capability or workflow"
```

Colors are suggestions; adjust to match your palette. After labels exist, new issues opened via templates will receive the matching label automatically.
