# Architecture Overview

This document describes the high-level system design, including the agent orchestrator,
retrieval augmented guideline pipeline, and integration points with external systems
such as Nemotron NIM and FHIR-compliant EHR services.

sequenceDiagram
    participant RIS as Radiology System
    participant API as API Gateway
    participant Agent as Agent Orchestrator
    participant LLM as Nemotron NIM<br/>(Reasoning)
    participant EMB as Embedding NIM<br/>(Retrieval)
    participant VDB as Vector Database<br/>(Guidelines)
    participant EHR as EHR System
    participant Audit as Audit Logger

    Note over RIS,Audit: Example: Chest CT Report with Ground-Glass Nodule

    RIS->>API: POST /process-report<br/>{"report_text": "3mm GGN in RUL..."}
    API->>Agent: Initialize Processing
    
    rect rgb(255, 240, 200)
    Note over Agent,LLM: Step 1: Parse Report
    Agent->>Agent: Extract with regex + patterns
    Agent->>LLM: "Extract clinical findings from:<br/>[report text]"
    LLM-->>Agent: {"finding": "ground-glass nodule",<br/>"size": "3mm", "location": "RUL"}
    end

    rect rgb(200, 240, 255)
    Note over Agent,VDB: Step 2: Retrieve Guidelines
    Agent->>EMB: Embed query: "ground-glass<br/>nodule 3mm follow-up"
    EMB-->>Agent: Query vector [768 dims]
    Agent->>VDB: Vector similarity search
    VDB-->>Agent: Top 3 guideline chunks:<br/>1. Fleischner SSN <6mm<br/>2. ACR lung nodule protocol<br/>3. Follow-up intervals
    end

    rect rgb(200, 255, 200)
    Note over Agent,LLM: Step 3: Reason About Recommendation
    Agent->>LLM: Prompt with context:<br/>"Finding: 3mm GGN<br/>Guidelines: [retrieved chunks]<br/>What follow-up is needed?"
    LLM-->>Agent: "Based on Fleischner 2017:<br/>Sub-solid nodule <6mm →<br/>CT chest in 6-12 months"
    end

    rect rgb(255, 220, 255)
    Note over Agent,LLM: Step 4: Safety Validation
    Agent->>LLM: "Check for contradictions:<br/>Patient history, prior imaging,<br/>other findings"
    LLM-->>Agent: "No conflicts detected.<br/>Recommendation is appropriate."
    end

    rect rgb(255, 200, 200)
    Note over Agent,EHR: Step 5: Generate Task
    Agent->>Agent: Build FHIR ServiceRequest:<br/>- Order: CT Chest<br/>- Timing: 6 months<br/>- Reason: Fleischner SSN protocol
    Agent->>EHR: POST FHIR ServiceRequest
    EHR-->>Agent: Order created: RAD-2025-12345
    end

    Agent->>Audit: Log decision:<br/>- Finding details<br/>- Retrieved guidelines<br/>- Reasoning trace<br/>- Order ID
    
    Agent->>API: Response:<br/>{"status": "success",<br/>"order_id": "RAD-2025-12345",<br/>"follow_up": "CT in 6 months"}
    API->>RIS: 200 OK

    Note over RIS,Audit: Processing time: ~3-5 seconds