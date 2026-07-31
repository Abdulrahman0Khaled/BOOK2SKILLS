# Security Policy 🛡️

The **Book2Skills** team takes the security of our software, data pipelines, and user deployments very seriously. We appreciate the contributions of security researchers and the open-source community in helping us keep Book2Skills secure.

This document outlines our security policies, supported versions, and the process for reporting vulnerabilities.

---

## 📋 Supported Versions

We provide security updates and patches for the following versions of **Book2Skills**:

| Version | Supported | Security Maintenance Status |
| :--- | :---: | :--- |
| `1.0.x` | ✅ Yes | **Active Security Maintenance (Latest Stable)** |
| `< 1.0` | ❌ No | Unsupported (Please upgrade to `v1.0.0`+) |

---

## 🔒 Reporting a Vulnerability

If you discover a security vulnerability within **Book2Skills**, please follow responsible disclosure practices. **Do NOT report security vulnerabilities through public GitHub Issues.**

### How to Submit a Security Report

Please report security issues privately via email or GitHub Security Advisories:

- 📧 **Private Security Email**: `abdulrahman.helmadin@gmail.com`
- 🔐 **GitHub Advisory**: Submit via [GitHub Security Advisories](https://github.com/Abdulrahman0Khaled/BOOK2SKILLS/security/advisories/new)

### What to Include in Your Report

To help us investigate and resolve the issue quickly, please include:
1. **Type of Vulnerability**: (e.g., Arbitrary Code Execution, Prompt Injection, Insecure Deserialization, API Key Exposure).
2. **Step-by-Step Reproduction**: Detailed steps or a minimal Proof-of-Concept (PoC) script.
3. **Affected Component**: The specific module, file, CLI command, or API endpoint (`fastapi`, `pypdf`, `chromadb`, LLM provider adapter).
4. **Impact Assessment**: Estimated severity and potential risk to users or production infrastructure.
5. **Suggested Mitigation**: (Optional) Recommended code fixes or workaround strategies.

---

## ⏱️ Response Timelines

We commit to the following response SLA for reported security issues:

| Stage | Target Response Time |
| :--- | :--- |
| **Initial Acknowledgment** | Within **48 hours** |
| **Severity Assessment & Triaging** | Within **5 business days** |
| **Patch Development & Release** | **Critical**: < 7 days \| **High**: < 14 days \| **Medium/Low**: < 30 days |

---

## 🛡️ Production Security Guidelines

When deploying **Book2Skills** in production environments, adhere to the following security best practices:

### 1. API Keys & Secrets Management
- Never commit `.env` files or API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.) to source control.
- Use environment variables or secret managers (e.g., HashiCorp Vault, AWS Secrets Manager, Kubernetes Secrets).
- Rotate API keys periodically and use restricted-scoped keys.

### 2. Document Extraction & File Handling
- Sanitize incoming book files (`.pdf`, `.docx`, `.epub`) before passing them to parsing engines.
- Run document extraction stages inside containerized/sandboxed environments (e.g., Docker) to mitigate untrusted file execution risks.

### 3. Local Model & RAG Vector Database Security
- Bind ChromaDB and Local LLM endpoints (`Ollama`, `vLLM`) to `localhost` (`127.0.0.1`) or secure internal networks behind authenticated proxies.
- Enforce network encryption (TLS/HTTPS) for remote API calls.

---

## 📜 Public Disclosure Policy

Once a security issue is reported:
1. We will work with the reporter to confirm and reproduce the vulnerability privately.
2. A patch will be authored, reviewed, and tested in a private security advisory branch.
3. A security advisory and patched release (e.g., `v1.0.1`) will be published simultaneously on GitHub.
4. Credit will be given to the security researcher in the release notes (unless anonymity is requested).

---

Thank you for keeping **Book2Skills** and our community safe! 🛡️
