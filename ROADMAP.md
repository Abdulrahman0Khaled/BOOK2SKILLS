# Book2Skills Product Roadmap 🗺️

Welcome to the **Book2Skills** product roadmap! This document outlines our core architecture, current achievements, and planned strategic phases for building the ultimate autonomous book-to-AI-skill conversion pipeline.

> **Our Mission:** To bridge human domain literature and AI agent intelligence by converting unstructured books into structured, executable, high-precision **Hermes Skills**.

---

## 📅 Strategic Phases Overview

```
Phase 1: Core Release (Current) ──► Phase 2: Multimodal & Scale ──► Phase 3: Web UI & Fine-Tuning ──► Phase 4: Agent Ecosystem
```

---

## ✅ Phase 1 — Core Production Release (Current Stable)

- [x] **Multi-Format Document Extraction**: Native parsing for PDF, DOCX, EPUB, TXT, HTML, and Markdown files.
- [x] **Multi-Provider LLM Engine**: Unified abstraction for Ollama (local), OpenAI (GPT-4o), Anthropic (Claude 3.5), Google Gemini, DeepSeek, and OpenRouter.
- [x] **10-Stage Pipeline Architecture**: Extraction ➔ Cleaning ➔ Chunking ➔ Knowledge Extraction ➔ Skill Generation ➔ LLM Quality Audit ➔ Vector Embeddings ➔ ChromaDB Storage ➔ Deduplication ➔ Graph Mapping.
- [x] **Interactive TUI Studio (`book2skills studio`)**: Full keyboard-navigable terminal interface with live visual progress tracking.
- [x] **Semantic Deduplication**: Cosine similarity clustering (0.85+ threshold) preventing duplicate skill creation.
- [x] **Automated Hermes Export**: One-click generation of formatted `SKILL.md` bundles with workflows, checklists, and edge-case handling.
- [x] **Documentation & CI/CD**: MkDocs Material site hosted on GitHub Pages with automated CI/CD deployment.

---

## 🚀 Phase 2 — Multimodal Extraction & Distributed Scalability

Focusing on vision capabilities, diagram extraction, custom prompt overrides, and distributed workload execution.

- [ ] **Multimodal Vision Parsing**: Integrate Vision LLMs (GPT-4o Vision, Claude 3.5 Sonnet, Qwen2-VL) to extract tables, architecture diagrams, and flowcharts directly from PDF/EPUB books.
- [ ] **Custom Skill Extraction Templates**: Allow users to define custom YAML/Jinja templates for domain-specific skill extraction formats (e.g., Medical, Legal, Software Engineering).
- [ ] **Distributed Async Workers**: Expand Redis/RQ task queue to support distributed multi-node worker nodes for processing 100+ books concurrently.
- [ ] **Advanced Chunking Strategies**: Implement Semantic Header-aware chunking and Recursive Character Text Splitter with dynamic token windows.

---

## 🎨 Phase 3 — Web Workspace & Fine-Tuning Dataset Exporter

Expanding user accessibility with a modern web dashboard and bridging skills into LLM training datasets.

- [ ] **Web GUI Workspace**: A modern, rich web-based dashboard (FastAPI + React/Next.js) for visual pipeline management, skill editing, and user collaboration.
- [ ] **Synthetic Dataset Exporter for Fine-Tuning**: Export generated Hermes skills directly into JSONL formats (ShareGPT, Alpaca, DPO pairs) for fine-tuning open-source models (Llama 3, Qwen 2.5).
- [ ] **Interactive 3D Knowledge Graph**: Embedded WebGL / D3.js interactive visualizer for exploring inter-skill dependencies and relationship clusters.
- [ ] **REST API Webhook System**: Real-time event webhooks for pipeline start, stage completion, and quality score alerts.

---

## 🌐 Phase 4 — Multi-Agent Ecosystem & Multi-Lingual Intelligence

Integrating with leading AI agent frameworks and enabling native multi-language skill synthesis.

- [ ] **Native Agent Runtimes Integration**: Direct plugin adapters for **Hermes**, **CrewAI**, **AutoGen**, **LangChain**, and **LlamaIndex**.
- [ ] **Native Multi-Lingual Synthesis**: Dedicated pipeline optimizations for synthesizing skills natively in Arabic, English, Spanish, French, and Japanese without translation loss.
- [ ] **Autonomous Skill Self-Improvement**: Feedback loop mechanisms where active AI agents score skill utility in real time and automatically trigger pipeline refinement.
- [ ] **Enterprise Role-Based Access Control (RBAC)**: Multi-tenant database partitioning and user permission management for enterprise teams.

---

## 🗣️ Community Feedback & Contributions

We build **Book2Skills** in the open, and community feedback shapes our development priorities:

- **Vote on Features**: Browse our [GitHub Issues](https://github.com/Abdulrahman0Khaled/BOOK2SKILLS/issues) and add a 👍 reaction to features you want prioritized.
- **Start a Discussion**: Share your use case or suggest new capabilities in [GitHub Discussions](https://github.com/Abdulrahman0Khaled/BOOK2SKILLS/discussions).
- **Contribute**: Check out our [CONTRIBUTING.md](CONTRIBUTING.md) guide to help build any phase listed above!
