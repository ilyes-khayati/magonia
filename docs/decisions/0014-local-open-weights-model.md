# 0014. A local open-weights model behind a one-method provider protocol

Status: accepted

## Context
Researchers' unpublished data and notes should not leave their network, a question should
cost nothing, and the capstone's claim is that engineering around a small model (routing,
retrieval, code checks) makes it trustworthy.

## Decision
qwen2.5:7b served by Ollama on a machine of the local network (`MAGONIA_MODEL_URL`), behind a
`Provider` protocol with one streaming method. A `Scripted` provider gives fixed answers for
tests and for running without a model.

## Consequences
Free, private, offline-capable; slower and weaker at long synthesis than a hosted frontier
model. A hosted model is a new provider class of about 50 lines, and the checks keep working
unchanged because they never trusted the model in the first place.
