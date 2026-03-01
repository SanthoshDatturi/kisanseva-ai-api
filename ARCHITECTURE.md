# Building Scalable AI Workflows with Long-Running, Reliable Processes

Modern AI services often involve multi-step, long-running tasks (for example: document analysis, report generation, or agent workflows). These tasks may produce **large nested JSON outputs**, can **fail mid-way**, and users expect **real-time progress updates**.  A robust design combines proven architectural patterns (Saga, State Machines, Outbox/event streaming, etc.) with streaming generation techniques. The result is a system where each step’s result is **persisted**, failures are **containable**, and the frontend sees incremental output as it’s produced.  

This guide covers:  
- **Orchestration Patterns** (Saga, State Machines) to manage multi-step workflows with failures and compensations.  
- **Reliable Messaging** (Transactional Outbox, Event Streams) to make step state updates durable and decoupled.  
- **Streaming Model Output** (NDJSON and incremental parsing) to push partial results to the UI.  
- **Prompting and Parsing** strategies to drive and consume structured AI outputs in real time.  

Throughout, we avoid any specific language or model (so the ideas apply to any ML service stack), and use examples (pseudo-code, diagrams) for clarity. 

---

## Saga & State Machine for Multi-Step Workflows

**Multi-step operations** (place order, analyze document, process payment, etc.) cannot fit in one database transaction, especially across services. The **Saga pattern** orchestrates such long-running processes by breaking them into **local transactions** that each update state and trigger the next step【26†L98-L107】【5†L69-L74】.  Each step either succeeds or triggers a **compensation** (undo) if it fails.  In effect, a saga is a **state machine** over the workflow’s steps, storing “where we are” so it can recover or retry after failures【5†L69-L74】【26†L98-L107】. 

For example, an “Analysis Saga” might have steps: *[extract text]→[classify data]→[summarize]*.  The orchestration ensures each step only runs if the previous succeeded. If *Step 2* fails, the saga could stop (or run compensations like releasing resources) and mark the overall task as failed. This gives **all-or-nothing** semantics: either all steps complete or compensations run to undo earlier steps【26†L98-L107】【5†L69-L74】.  

**State Machines:** Internally, the saga is implemented as a state machine. The process has explicit states (e.g. `PENDING→IN_PROGRESS→COMPLETED` or step-specific states `PENDING→IN_PROGRESS→DONE/FAILED`).  Each state transition is recorded in the database along with a human-readable “state-info” (for debugging/user messages)【7†L229-L237】.  For instance, when a step starts, write `state="IN_PROGRESS", step=2, stateInfo="Classifying transactions..."`. On success, transition it to `DONE`, on error to `FAILED`. By storing all state changes in one transaction (DB update + outbox insert, see below), we avoid races【7†L229-L237】. 

We typically include **timeouts and retries**: if a step’s state has been `IN_PROGRESS` for too long, an external timer or cleanup job can retry or fail it. Each transition is guarded: code checks “am I allowed to do this action in the current state?” (e.g. don’t start a step again if it’s already done)【7†L229-L237】.  This ensures the workflow is deterministic and recoverable after crashes.  

**Choreography vs Orchestration:** Two saga styles exist. With *choreography*, each service publishes events after its step, and others listen to advance the flow. With *orchestration*, a central coordinator (or orchestrator service) issues commands in sequence.  For complex AI workflows (especially if you want to monitor overall progress), an **orchestration model** often makes sense: a central saga controller updates state and dispatches each step, listening for success/failure before moving on【26†L98-L107】.  This controller can be a dedicated microservice or even a stateful workflow engine (like Temporal, AWS Step Functions, etc.), but at its core it follows the saga/state-machine logic described above. 

**Summary of key benefits:** The saga+state-machine approach ensures that **no intermediate work is lost** on failure. Completed steps remain done, and the system knows exactly which step to resume. It also enables **compensation** logic: if needed, earlier steps can be undone (e.g. refunding a payment if downstream fails)【26†L98-L107】. Crucially, the saga is the “source of truth” for where the workflow stands, even if the server restarts or a step has to be retried.

---

## Outbox & Event Streaming for Reliability

To make each step’s status visible and durable, we combine the above with an **event-driven** approach (e.g. Kafka, Redis Streams). Each state change in the saga is published as an event. For example, when step 1 completes, we publish an event `{"workflowId":123, "step":1, "status":"DONE"}`. Any interested party can subscribe: the next worker may consume it to start step 2, and a UI gateway can consume it to push updates to the client. 

A critical detail: these state-updates+events must be **atomic** with the database change. Otherwise you risk a “dual-write” bug (DB updated but event lost, or vice versa). The **Transactional Outbox Pattern** solves this: instead of writing directly to a message broker, each service writes its outgoing events into a local “outbox” table in the same DB transaction that it uses to update its state【3†L57-L64】【28†L85-L92】. After commit, a separate process (typically a CDC connector or background poller) reads that outbox table and publishes to the message broker. 

In practice this means:
- **Step execution code**: begin transaction → update step/status in the workflow table **and** insert a row into `Outbox(eventType, payload, status=PENDING)` → commit.  
- **Outbox publisher**: independently, a daemon reads rows with `status=PENDING`, sends them to Kafka/Redis, then marks them sent.  

This guarantees *at-least-once* delivery of events, with no possibility of the DB change being visible without the event (or vice versa)【3†L57-L64】【28†L85-L92】. For example, “Step1 DONE” event will never be dropped if the database shows step1 done, even if the service crashed right after committing.  

**Event Flow Benefits:** Using a durable log (Kafka, Redis Streams, etc.) gives several advantages.  It decouples producers and consumers (so the worker for step N doesn’t need to know about the UI).  It provides **ordering guarantees** per workflow, so steps are processed in order. It allows **scaling out** (multiple consumers can share the load). And it naturally keeps a history of all step events for auditing or replays.  

For the front-end, a separate “gateway” service can consume the same stream and push updates via WebSockets or Server-Sent Events. Or we can let the client poll a status endpoint (backed by the same state machine). Either way, the **outbox + event stream** approach ensures nothing gets lost and the UI can show progress or final notifications reliably.

---

## Streaming Model Output with NDJSON

In many AI tasks, one of the steps is calling an LLM or generative model that produces a **large JSON object or list** (e.g. analyzing a document and outputting structured data). Waiting for the full response wastes time. Instead, we stream partial results *as soon as they are ready*.  

The simplest streaming for text is just sending tokens/chunks. But for structured JSON output, we need to ensure each partial output is valid or parsable. A common solution is **Newline-Delimited JSON (NDJSON)**: have the model output *one JSON object per line*. Each line is self-contained and parseable. The service can emit each completed object immediately to the client. 

### Prompting for NDJSON
To use NDJSON, the LLM must be instructed carefully. For example, the prompt might say: “Output the answer as a sequence of JSON objects, one per line. Do not wrap them in an array and do not output any extra text. For example:  
```
{"step":1,"result":...}
{"step":2,"result":...}
...
```  
Each line must be valid JSON.”  

This forces the model to emit line-by-line JSON. In practice, you often define a small schema for each JSON object and explicitly tell the model to follow it.  The curated code example [13†L318-L322] shows a final streamed output:  
```json
{"$type":"todoListCreated","listName":"Bucket List"}
{"$type":"todoListItemAdded","recommendedAge":30,"description":"Skydiving"}
{"$type":"todoListItemAdded","recommendedAge":50,"description":"Visit all seven continents"}
```  
Each line is one JSON event (type `todoListCreated` or `todoListItemAdded`). Our backend service can parse each line independently and treat it as a “step completed” event【16†L318-L322】. 

### Incremental Parsing (State Machine)
If for some reason NDJSON isn’t fully reliable (model occasionally breaks format), or you truly need to stream a single JSON document, you can incrementally parse the JSON stream. This uses a state machine that consumes tokens as they arrive and emits events when a sub-structure is complete. For example, as each key-value pair or list item is fully read, emit an event. The [Semantic Kernel example](#) uses a state-machine-driven JSON parser that recognizes fields like `"listName"`, `"items"`, etc., and builds each output event as soon as it’s parsed【16†L422-L432】【16†L434-L442】. 

The core idea is: don’t wait for `}` of the entire JSON. Instead, track the reader’s state so when it finishes reading one list item or one object, you output it to the client and clear that part of the buffer. This is complex to implement (you need to handle strings, escapes, braces count, etc.), but it can let you stream valid NDJSON from a single JSON stream.

In most cases, NDJSON is easier: each time you encounter a newline from the model, parse that line as JSON. If it’s valid, send it onward. If the model inserts spaces or accidental breaks, you can buffer until a valid JSON object is formed. Many examples (like the [NDJSON parser for .NET](#)) show how to accumulate text and count braces or newlines to decide when a complete JSON object is ready【16†L289-L293】【16†L318-L322】.

### Streaming to the Frontend
Once the backend has parsed JSON pieces (each representing a “step result” or partial output), it sends them to the client. A common approach is using Server-Sent Events (SSE) or WebSockets to push updates. For SSE, set `Content-Type: text/event-stream` and then stream lines like:
```
event: stepDone
data: {"step":1,"result":...}

event: stepDone
data: {"step":2,"result":...}
```
or even simpler, `data: JSON\n\n` for each line (JSONL). The frontend concatenates or processes each JSON blob as it arrives. 

Alternatively, if using HTTP, the backend can respond with `Content-Type: application/x-ndjson` and simply write one JSON-per-line. The client can use `fetch()` with a `ReadableStream` to read chunks and split on newlines. In all cases, the user sees partial output appear quickly (no “spinning” for the whole answer). As one example note explains: “It can be frustrating for users to wait for completion… The best solution is to display the generated content incrementally”【16†L289-L293】.

In summary, streaming model output in NDJSON lets your UI show progress (each object can correspond to “step 2 done” and include some content). This plays nicely with the saga state machine: when the model emits JSON for step N, you mark step N as completed (saving to DB) and push the event out. 

---

## Bringing It All Together: End-to-End Workflow

Imagine an **AI document processing service**. The user uploads a PDF; we want to (1) OCR it, (2) parse the text with an LLM into structured JSON, (3) run analytics on that JSON, (4) finalize a report. The user’s frontend must see progress through these stages.

1. **Start:** Frontend calls `POST /api/analysis` with the document. Backend creates a new **Process record** in the DB (`state=PENDING`, id=XYZ) and immediately responds with the `id`.  

2. **Saga/Orchestrator:** A background orchestrator (or simply the same service) now executes steps in sequence. It updates `state=IN_PROGRESS` and `currentStep=OCR`. Using a DB transaction+outbox, it marks step 1 started and publishes a “Step1Started” event.  

3. **Step 1 – OCR:** A worker (could be the same service or separate) picks up the “Step1Started” event (or is invoked directly). It performs OCR, saves text to storage, then in one transaction updates `process_state` to include `step1=done` and writes an outbox message “Step1Done”. After commit, the message broker (Kafka/Redis) gets “Step1Done”.  

4. **Notify Frontend:** The same “Step1Done” event can be consumed by a WebSocket gateway which forwards it to the client, or the client polls an endpoint. The user sees “Step 1 complete”.  

5. **Step 2 – LLM Parsing:** The orchestrator now triggers step 2: it calls the LLM with a prompt to extract structured data from the OCR text. The LLM prompt is written to produce NDJSON output (or use incremental parsing). As the LLM streams its response, our backend parses each JSON object and, for each, does:
   - Save the object in DB (e.g. a `ParsedItem` table).
   - Emit an event like “ParsedDataChunk” (could also use outbox).
   - Update `currentStep=Step2` with progress if needed (optional).  

   Meanwhile, the partial JSON is forwarded to the client (via SSE/WebSocket). The user might see items appearing in real-time.  

6. **Step 3 – Analysis/AI Check:** Once parsing completes, orchestrator triggers step 3 (maybe calling another model or a rule engine on the parsed data). It repeats the same pattern: call worker, worker does its work, writes final data & events, etc.  

7. **Completion:** After step N, orchestrator marks `state=COMPLETED` and emits a final event. The client is notified and can display the full result.  

8. **Failure and Retry:** If any step fails (e.g. the LLM times out or the analysis throws an error), the worker updates that step’s state to `FAILED` in the DB (via transaction+outbox) and emits a “StepFailed” event. The orchestrator stops or triggers compensations. The frontend sees “Step X failed”. The user or system could then call an API to retry that step; the orchestrator will see “last completed step = 1” and resume from step 2.  

Throughout this flow, each **state update** and **event emission** is atomic (via outbox)【3†L57-L64】【28†L85-L92】. Each **step output** is stored (so work isn’t lost). Each event triggers the next work and updates the UI. This is exactly the Saga + Event-Driven pattern in action. 

---

## Practical Tips

- **Schema and Prompts:** Always define a clear JSON schema for the model to output. Show an example in the prompt. For instance:  
  ```text
  “Structure the answer as NDJSON, one object per line, with fields {step:int, result:string}. Example output:
  {"step":1,"result":"..."}
  {"step":2,"result":"..."}…”
  ```  
  This constrains the model.  

- **Validate and Retry:** Use schema validation (e.g. JSON Schema or Zod) on each streamed JSON object. If the model’s output isn’t valid JSON, you can buffer and retry or skip. Maintain a **retry buffer** for malformed lines.  

- **Deduplicate Events:** Because streams are at-least-once, assign a unique ID to each event/step so consumers can ignore duplicates. Our Saga DB can also dedupe by checking if a step’s result already exists.  

- **HTTP vs SSE:** If your front end can handle EventSource, SSE is very simple for pushing NDJSON. If not, you can use a long-polling or WebSocket approach. The key is to not wait for the entire model completion before sending data.  

- **State Timeouts:** For each intermediate state (like a step in progress), consider a timeout. If a step exceeds expected time, have a watchdog that marks it `FAILED` and notifies.  

- **Monitoring:** Log and monitor each state transition. You now have a fine-grained audit trail (in your DB and in the message log). Tools like OpenTelemetry can trace the saga across steps.  

- **Scalability:** If steps become heavy (e.g. high-throughput LLM calls), you can parallelize independent sub-steps by having multiple worker instances consume the relevant events. The message queue handles load leveling. 

---

## Summary

By combining **Saga orchestration** (orchestration + compensation), **state machines**, and **outbox/event streaming**, we build AI services where each step of a long-running generation or reasoning process is tracked and recoverable. Persistent state and events ensure nothing is lost on failures. Streaming techniques (like NDJSON) let us push partial model outputs to users for a responsive UI. 

In short, treat your multi-step AI task *like an order fulfillment*: break it into steps, record progress, publish events, and handle failures gracefully. When each step’s result (even deep nested JSON) is saved and streamed, you get a robust, user-friendly AI service. 

**Key references:** Saga pattern for long transactions【26†L98-L107】【5†L69-L74】; State Machine design for resource lifecycles【7†L229-L237】; Transactional Outbox for reliable events【3†L57-L64】【28†L85-L92】; NDJSON streaming for incremental model output【16†L280-L287】【16†L318-L322】.