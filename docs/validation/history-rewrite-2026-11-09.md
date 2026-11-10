# History rewrite: old and new commit IDs

## What changed and why

At the owner's request, the commit messages of this repository were rewritten. The lines that named
Claude as a co-author were removed. GitHub's `main` was replaced with the rewritten history on
2026-11-10. The backup of the old history is dated 2026-11-09, which gives this file its name.

Only the commit messages changed. Each new commit has the same file tree as the old one, byte for
byte. Two messages that named an older commit by its ID now name the new ID. A commit ID is a hash
of the tree, the parents and the message, so every commit has a new ID.

Checked on 2026-11-10, in the local repository, which still had the old objects:

- `git rev-parse <old>^{tree}` and `git rev-parse <new>^{tree}` are equal for all 8 pairs.
- A diff of each old message against the new one shows only the removed `Co-Authored-By` line and
  the blank line before it. The exceptions are the two ID changes named above (in the messages of
  `f74c6e3` and `9fb7403`).

## The map

Oldest first. Use the new ID for everything: `git show <new>:<path>` gives the same file that the
old ID gave.

| Old ID | New ID | Commit |
|---|---|---|
| `893c3a5b5beb723901ab58ebc71434c8e1d4ade6` | `02546b92ebfe1b17537354e8bb27548d974eda0b` | Initialise repository |
| `9cd2f19b4f925575696da5d7c0867d75296d670d` | `fc33a9dc0153ddf04718fc2ccca4a30fd59e7ec7` | Milestone 0: foundations — scaffold, JSON contract, ADRs, design, concepts |
| `046fd8fee1ba7fc17f25bd86df3fb2946392b276` | `165890a8a45b46c47c02d1f3048a92a4081cfb20` | Re-export app data so it names the milestone-0 commit |
| `5782703ff9fa893313b2d6801b8e4c18027966a3` | `eed26840350776f965124c23943fa44dfd2acfa2` | Milestone 1: option-chain data layer, quality flags, calendar, DoltHub mask |
| `35cb68269034d995e39f17d63bc907f5779ed5b4` | `4a50af4a7981fa82b43f9997647d9925e4309fc8` | Re-export app data so it names the milestone-1 commit |
| `86d9d5ae2a7885ca4f163e66b715bc6b4357fae1` | `248d200ea742834a0891389ec869aa535aaca61e` | Milestone 2: pricing core: Black-76, American IV, parity forwards, smiles |
| `e1edc18019a4e29c5eddb62e3f827890eae6306a` | `f74c6e319517ba362b45efd8c0b1ec0101c26f65` | Re-export app data so it names the milestone-2 commit |
| `f5cc66b751813e1233fc0aeb39fff6fb8522f82f` | `9fb7403a2ca4e974c3524d7ad43a2b63196685f0` | Learning log: queue the milestone-2 checkpoint (0 of 14 answered) |

## Old IDs you may still see

- **On GitHub.** The old commits are on no branch. GitHub may still show an old commit through a
  direct link to its ID for some time.
- **In old commits.** The files of the commits above are unchanged, so they still name old IDs.
  For example, the app data in `9fb7403` names `86d9d5a` as its `source_commit`. Read such an ID
  through the map.
- **In run ledgers.** The engine's run ledgers are in `data/runs/`, which git ignores. A run made
  before the rewrite records the old ID of its commit (for example `f5cc66b…-dirty`). The run id is
  a hash that includes that commit, so these ledgers were left as they are. Read their commit
  through the map.

## What was updated

From this commit on, every tracked file names the new IDs. This commit changed 11 files: the four
app data files (`source_commit`), `docs/architecture/README.md`, the knowledge graph
(`docs/architecture/graph/GRAPH_REPORT.md` and `graph.json`), `docs/milestones/00-foundations.md`,
`docs/validation/01-ledger.md`, `docs/validation/02-ledger.md` and `tools/diagrams/README.md`. Each
change replaces an old ID with the new ID of the same length.

To check a tree, run this from the repository root. It prints nothing when no tracked file other
than this one names an old ID:

```bash
git grep -nE '(893c3a5|9cd2f19|046fd8f|5782703|35cb682|86d9d5a|e1edc18|f5cc66b)' -- ':!docs/validation/history-rewrite-2026-11-09.md'
```
