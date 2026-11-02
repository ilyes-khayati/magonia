# 0010. Soft deletion with a 30-day purge

Status: accepted

## Context
A researcher who deletes a workspace, an area, a conversation or a file by mistake loses
work that may have taken days. Confirmation dialogs are clicked through by habit.

## Decision
Deleting sets a `deleted` timestamp; everything that lists or reads ignores deleted rows.
Undo (⌘Z, or the bar that appears) clears the timestamp; "Recently deleted" lists what can
be restored. Rows deleted more than 30 days ago are removed for good at start-up. A
workspace can also be deleted for good on purpose.

## Consequences
No confirmation dialogs, and nothing lost by a slip. Every query must remember the
`deleted IS NULL` filter, and a unique name stays taken while its owner is in the bin.
