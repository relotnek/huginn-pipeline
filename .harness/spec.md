<project_specification>
  <project_name>Huginn — Skill-Based LLM Pipeline System</project_name>

  <overview>
    Huginn is a two-part system for creating, validating, and running autonomous
    LLM pipelines on local infrastructure.

    Part 1 — The Orchestrator: A frontier model (Claude Opus via API) that helps
    you design pipelines interactively. You describe what you want ("a post generator
    that writes LinkedIn content in my voice"), and the Orchestrator walks through
    a structured creation cycle: Research → Design → Validate → Threat Model →
    Build → Test. The output is a pipeline folder with skill files, a manifest,
    and everything needed to run autonomously.

    Part 2 — The Runner: Executes validated pipelines on local hardware (i3 server,
    Mac, Pi cluster). Each pipeline is a chain of sub-agents, each with its own
    model, skill, tools, prompts, and reference files. The Runner manages sandboxing,
    checkpointing, parallel execution, and resource allocation.

    The key insight: frontier intelligence designs the pipelines (once), local models
    execute them (repeatedly, for free). You pay for Opus during the design phase,
    then run the result thousands of times on your own hardware at zero marginal cost.
  </overview>

  <technology_stack>
    <runtime>Python 3.11+ CLI application</runtime>
    <integrations>
      <anthropic_api>Claude Opus 4.6 for Orchestrator (pipeline design, skill authoring)</anthropic_api>
      <ollama>Local model inference via OpenAI-compatible API for Runner</ollama>
      <docker>Worker sandboxing — each sub-agent runs in an isolated container</docker>
      <sqlite>Task queue, run history, checkpoint storage, pipeline registry</sqlite>
    </integrations>
    <state_management>
      SQLite database at ~/.huginn/huginn.db
      Pipeline definitions in ~/.huginn/pipelines/{name}/
      Global skills library in ~/.huginn/skills/
      Task working directories in ~/.huginn/tasks/{task_id}/
    </state_management>
  </technology_stack>

  <core_concepts>

    <concept name="pipeline">
      A pipeline is a folder containing everything needed to execute a
      multi-stage autonomous workflow. It is the primary artifact Huginn
      produces and runs.

      Structure:
      ~/.huginn/pipelines/post-generator/
      ├── manifest.yaml           # Pipeline definition: stages, models, routing
      ├── skills/                 # Stage-specific skill files
      │   ├── 01-researcher.md
      │   ├── 02-writer.md
      │   ├── 03-slop-filter.md
      │   └── 04-voice-check.md
      ├── prompts/                # Reusable prompt templates referenced by skills
      │   └── ken-voice-rules.md
      ├── tools/                  # Custom tool definitions for this pipeline
      │   └── word-counter.py
      ├── files/                  # Reference files skills can read
      │   ├── style-guide.md
      │   └── example-posts.md
      ├── validation/             # Artifacts from the creation cycle
      │   ├── research.md
      │   ├── design.md
      │   ├── threat-model.md
      │   └── test-results.md
      └── README.md

      The manifest.yaml defines the execution graph:

      name: post-generator
      description: Generate LinkedIn posts in Ken's voice from source material
      version: 1.0
      created_by: orchestrator
      validated: true
      threat_modeled: true

      defaults:
        backend: i3
        timeout_minutes: 60

      stages:
        - name: analyze
          skill: skills/01-researcher.md
          model: qwen3:8b
          backend: i3
          input: $pipeline_input
          output: analysis.json
          tools: [file_read]
          constraints:
            network: false
            shell: false

        - name: draft
          skill: skills/02-writer.md
          model: qwen3:30b-a3b
          backend: i3
          input: analysis.json
          files: [files/style-guide.md, files/example-posts.md]
          output: draft.md
          tools: [file_read, file_write]
          constraints:
            network: false
            shell: false

        - name: slop-filter
          skill: skills/03-slop-filter.md
          model: qwen3:8b
          backend: i3
          input: draft.md
          output: slop-report.json
          tools: [file_read]

        - name: revise
          skill: skills/04-voice-check.md
          model: qwen3:30b-a3b
          backend: i3
          input:
            - draft.md
            - slop-report.json
          files: [files/style-guide.md]
          output: final-post.md
          tools: [file_read, file_write]
          verification:
            - "Output is 150-300 words"
            - "No banned phrases from style guide"
            - "First sentence is operational reality, not a hot take"

      on_complete:
        output_file: final-post.md
    </concept>

    <concept name="skill">
      A markdown file that defines a single sub-agent's operating context.
      Skills are the intelligence layer — they make cheap models smart on
      narrow tasks.

      Skills can live in a pipeline's skills/ folder (pipeline-specific)
      or in the global ~/.huginn/skills/ library (reusable across pipelines).

      Format: YAML frontmatter + markdown body.

      ---
      name: linkedin-writer
      model: qwen3:30b-a3b
      backend: i3
      temperature: 0.7
      max_iterations: 5
      tools: [file_read, file_write]
      constraints:
        network: false
        shell: false
        timeout_minutes: 30
      ---

      # LinkedIn Writer — Ken's Voice
      [Full system prompt with voice rules, banned phrases, calibration examples]

      ## Input
      Read analysis.json from the input directory.

      ## Output
      Write a LinkedIn post to output/draft.md.

      ## Verification
      1. No sentence stops and poses
      2. No banned phrases
      3. 150-300 words
      4. Starts with operational reality
      5. Ends human, not with a mic drop
    </concept>

    <concept name="orchestrator">
      The Orchestrator is a CLI mode that uses Claude Opus (via Anthropic API)
      to help you design, validate, and build pipelines interactively.

      Run: huginn create "a post generator for LinkedIn in my voice"

      The Orchestrator enters an interactive session:

      1. RESEARCH: Opus examines your existing skills library, available models
         (queries Ollama for what's pulled), reference files, and existing
         pipelines. Asks clarifying questions.

      2. DESIGN: Proposes pipeline architecture — stages, models per stage,
         skills to write or reuse, tools needed, files to reference.
         Presents as a design doc for review. Iterate.

      3. VALIDATE DESIGN: Reviews design against research — does it address
         requirements? Are model choices justified? Gaps?

      4. THREAT MODEL (optional): STRIDE analysis on the pipeline. What if a
         stage hallucinates? Malicious input propagation? Data exposure?
         Failure modes?

      5. VALIDATE THREAT MODEL: Checks mitigations are in the design.

      6. BUILD: Generates pipeline folder — manifest, skills, prompts, files.

      7. TEST: Runs pipeline on sample input. Reviews output against design.
         Iterate on specific stages.

      Each phase can circle back to prior phases. All artifacts are stored
      in the pipeline's validation/ folder.

      Also supports refinement:
      huginn refine post-generator "the slop filter misses rhythmic three-beat lists"
    </concept>

    <concept name="runner">
      Executes validated pipelines. Reads manifest, creates task directory,
      executes stages in order. Each stage runs in a Docker container.

      Per stage:
      1. Build container with stage's skill, model config, tool access
      2. Mount input (read-only): output from previous stage or pipeline input
      3. Mount files (read-only): reference files from manifest
      4. Mount output (read-write): where this stage writes results
      5. Run agent loop (observe → think → act → verify → checkpoint)
      6. On completion, pass output to next stage
      7. On failure, stop pipeline and preserve partial output
    </concept>

    <concept name="agent_loop">
      Generic worker agent inside each container:

      load skill from /task/skill.md
      load checkpoint if exists (resume)
      load input and reference files

      while iterations less than max_iterations and not complete:
          OBSERVE: read current state
          THINK:   call Ollama with skill_prompt + state
          ACT:     execute response (write file, run tool)
          VERIFY:  check output against skill verification rules
                   if fail, feed failure into next iteration
          CHECKPOINT: save progress
          DECIDE:  complete? → done. stuck? → fail.

      write final status to meta.json
    </concept>

    <concept name="validation_cycle">
      Optional but encouraged discipline for pipeline creation.

      RESEARCH → What models, skills, tools, files are available?
          ↓
      DESIGN → Stages, models, skills, tools, data flow.
          ↓  ↑ (iterate until design satisfies research)
      THREAT MODEL → STRIDE on the pipeline. Failure modes. Data exposure.
          ↓  ↑ (iterate until mitigations are in design)
      BUILD → Generate pipeline folder.
          ↓
      TEST → Run on sample input. Pentest. UX test.
          ↓  ↑ (iterate until tests pass)
      VALIDATED → Ready for autonomous execution.

      For low-risk pipelines, skip threat model and go design → build → test.
      For anything touching client data, run the full cycle.
    </concept>

  </core_concepts>

  <directory_structure>
    ~/.huginn/
    ├── huginn.db                     # SQLite: tasks, stages, runs
    ├── config.yaml                   # Ollama endpoints, API keys, limits
    ├── skills/                       # Global reusable skill library
    │   ├── ken-voice-writer.md
    │   ├── content-classifier.md
    │   ├── exec-translator.md
    │   ├── code-reviewer.md
    │   ├── anti-slop-filter.md
    │   └── stride-analyzer.md
    ├── pipelines/                    # Pipeline definitions
    │   ├── post-generator/
    │   │   ├── manifest.yaml
    │   │   ├── skills/
    │   │   ├── prompts/
    │   │   ├── tools/
    │   │   ├── files/
    │   │   ├── validation/
    │   │   └── README.md
    │   ├── code-reviewer/
    │   ├── content-factory/
    │   └── slack-digest/
    ├── tasks/                        # Task execution directories
    │   └── {task_id}/
    │       ├── input/
    │       ├── stages/
    │       │   ├── 01-analyze/
    │       │   │   ├── input/
    │       │   │   └── output/
    │       │   └── ...
    │       ├── output/               # Final pipeline output
    │       └── meta.json
    └── worker/                       # Worker Docker image
        ├── Dockerfile
        ├── agent.py
        └── tools.py
  </directory_structure>

  <phases>
    <phase number="1">
      <title>Single Pipeline Runner</title>

      <philosophy>
        You can hand-write a pipeline folder (manifest + skills) and run it.
        `huginn run post-generator --input ./my-draft.md` executes every stage
        in order, each in its own sandbox, passing output forward. Tasks checkpoint
        and resume. Verification catches bad output. No Orchestrator yet — you
        write pipeline files yourself or with Claude in chat. If this phase never
        gets another update, it's still a useful tool for running any multi-stage
        LLM workflow safely and reproducibly on local hardware.
      </philosophy>

      <scope>
        <in_scope>
          - Pipeline manifest parser (YAML with stage definitions)
          - Skill file parser (YAML frontmatter + markdown body)
          - Sequential stage execution (stage N output → stage N+1 input)
          - Docker sandboxing per stage
          - Agent loop: observe → think → act → verify → checkpoint
          - Tools: file_read, file_write
          - Ollama API client (configurable backend per stage)
          - Checkpoint/resume at stage level
          - Verification engine
          - Timeout enforcement per stage and per pipeline
          - CLI: huginn run, huginn status, huginn pipelines, huginn skills
          - Task directory with per-stage isolation
          - Config file for endpoints and defaults
          - 3 starter pipelines: post-generator, content-classifier, code-reviewer
          - Error handling and graceful failure
        </in_scope>
        <out_of_scope>
          - Orchestrator (Phase 2)
          - Parallel execution (Phase 3)
          - Shell and network tools (Phase 2)
          - HTTP API (Phase 3)
          - Scheduled tasks (Phase 3)
          - Conditional stage routing (Phase 3)
        </out_of_scope>
      </scope>

      <features>
        <feature name="manifest_parser">
          <description>Parse and validate manifest.yaml — stages, wiring, constraints.</description>
          <verification>
            1. Create valid 3-stage manifest, run pipeline, verify all stages execute in order
            2. Reference nonexistent skill file, verify clear error naming the missing file
            3. Wire stage 2 to an output stage 1 doesn't produce, verify broken-wiring error
          </verification>
        </feature>

        <feature name="stage_executor">
          <description>Execute single stage in Docker with correct mounts and isolation.</description>
          <verification>
            1. Verify container appears during execution and is removed after
            2. Verify stage cannot see other stages' directories
            3. Verify network: false blocks internet but allows Ollama
            4. Verify resource limits apply (docker inspect)
          </verification>
        </feature>

        <feature name="stage_chaining">
          <description>Wire stage outputs to next stage inputs per manifest.</description>
          <verification>
            1. Stage 1 produces analysis.json, verify stage 2 can read it
            2. Stage 3 receives inputs from both stage 1 and stage 2
            3. $pipeline_input resolves to user-provided input file
          </verification>
        </feature>

        <feature name="agent_loop">
          <description>Generic agent: observe-think-act-verify-checkpoint.</description>
          <verification>
            1. max_iterations enforced, checkpoint shows correct count
            2. Verification failure triggers revision within iteration budget
            3. meta.json records verification pass/fail
          </verification>
        </feature>

        <feature name="checkpoint_resume">
          <description>Resume from last completed stage on rerun.</description>
          <verification>
            1. Kill during stage 3, rerun, verify stages 1-2 skipped
            2. Stage 3 resumes from checkpoint, not from scratch
            3. Final output matches uninterrupted run
          </verification>
        </feature>

        <feature name="cli">
          <description>huginn run, status, pipelines, skills commands.</description>
          <verification>
            1. huginn pipelines lists all pipelines with name and description
            2. huginn run {name} --input {path} executes and prints task ID
            3. huginn status {id} shows per-stage progress and timing
            4. huginn run with no args shows help
          </verification>
        </feature>
      </features>

      <testing>
        <test name="end_to_end">
          Run post-generator with source article. Verify: completes, stages run in
          order, final output exists, meta.json shows COMPLETE, containers cleaned up.
        </test>
        <test name="checkpoint_resilience">
          Kill during stage 3 of 4, rerun, verify resume and correct final output.
        </test>
        <test name="sandbox_isolation">
          Stage attempts read /etc/passwd, curl google.com, write to read-only mount.
          All blocked. Ollama access works.
        </test>
      </testing>

      <implementation_tasks>
        1. Project structure: huginn CLI, config loader, skill parser
        2. config.yaml parser (endpoints, defaults, limits)
        3. manifest.yaml parser with validation
        4. Skill file parser (YAML frontmatter + markdown)
        5. SQLite schema (tasks, stages, runs)
        6. Worker Docker image (agent.py + tools.py)
        7. Agent loop implementation
        8. file_read and file_write tools with path restrictions
        9. Ollama client (OpenAI-compatible, configurable endpoint)
        10. Verification engine
        11. Checkpoint/resume logic
        12. Stage executor (container lifecycle)
        13. Stage chaining (output → input wiring)
        14. huginn run command
        15. huginn status command
        16. huginn pipelines and huginn skills commands
        17. Timeout enforcement
        18. Container cleanup
        19. post-generator starter pipeline
        20. content-classifier starter pipeline
        21. code-reviewer starter pipeline
        22. End-to-end testing pass
      </implementation_tasks>
    </phase>

    <phase number="2">
      <title>Orchestrator — AI-Powered Pipeline Builder</title>

      <philosophy>
        Describe what you want in plain English, Opus designs the pipeline.
        huginn create "a threat model generator for client engagements" starts
        an interactive session — research, design, threat model, build, test.
        Iterate by talking. Pay for Opus once, run the result on local models forever.
      </philosophy>

      <scope>
        <in_scope>
          - huginn create and huginn refine commands
          - Anthropic API integration
          - Full validation cycle (research → design → threat model → build → test)
          - Shell and network tools with per-skill permissions
          - huginn benchmark (run stages against benchmark tasks)
          - Validation artifact storage
        </in_scope>
        <out_of_scope>
          - Parallel execution (Phase 3)
          - HTTP API (Phase 3)
          - Scheduled tasks (Phase 3)
          - Conditional branching (Phase 3)
        </out_of_scope>
      </scope>

      <implementation_tasks>
        1. Anthropic API client
        2. Research phase: scan models, skills, pipelines, benchmarks
        3. Design phase: Opus proposes, user iterates
        4. Threat model phase: STRIDE on pipeline
        5. Validation phase: check mitigations in design
        6. Build phase: generate pipeline folder
        7. Test phase: run and review
        8. huginn create interactive CLI
        9. huginn refine for existing pipelines
        10. Shell tool with allowlists
        11. Network tool with domain restrictions
        12. huginn benchmark command
        13. Validation artifact storage
      </implementation_tasks>
    </phase>

    <phase number="3">
      <title>Parallel Execution, API, and Scheduling</title>

      <philosophy>
        Huginn becomes infrastructure. Parallel pipelines, task queue, HTTP API,
        cron scheduling, conditional branching, cross-backend dispatch. Content
        factory runs nightly, Slack digest runs mornings, code reviewer triggers
        on PRs — all autonomously on local hardware.
      </philosophy>

      <scope>
        <in_scope>
          - Parallel execution with resource management
          - Task queue with priority
          - huginn batch, huginn daemon
          - HTTP API (FastAPI)
          - Scheduled/recurring pipelines (cron)
          - Conditional stage routing
          - Cross-backend dispatch
          - Webhooks on completion
          - huginn cancel, huginn logs
        </in_scope>
        <out_of_scope>
          - Web UI
          - Pi cluster orchestration
          - LoRA training integration
        </out_of_scope>
      </scope>

      <implementation_tasks>
        1. Task queue with priority and resource-aware scheduling
        2. Parallel worker tracking
        3. huginn batch command
        4. huginn daemon (background queue processor)
        5. FastAPI HTTP server
        6. API authentication
        7. Scheduled pipeline runner
        8. Conditional stage routing
        9. Cross-backend dispatch
        10. Webhook notifications
        11. huginn cancel and huginn logs
        12. Docker Compose for Huginn daemon
        13. Integration testing
      </implementation_tasks>
    </phase>
  </phases>

  <success_criteria>
    <phase_1>
      - Hand-written pipeline runs end-to-end with huginn run
      - Stages execute in isolated Docker containers
      - Output flows correctly between stages
      - Tasks survive interruption and resume
      - Verification catches bad output and triggers revision
      - 3 working starter pipelines
    </phase_1>
    <phase_2>
      - huginn create produces working pipeline from English description
      - Opus correctly inventories available models and skills
      - Threat model identifies real risks
      - Generated pipelines match hand-written quality
      - Refinement preserves what works, changes what doesn't
    </phase_2>
    <phase_3>
      - 10+ pipelines queue and process overnight
      - API accepts external task submissions
      - Recurring pipelines run on schedule
      - Resource limits prevent server overload
      - Cross-backend dispatch routes correctly
    </phase_3>
  </success_criteria>

  <database_schema>
    <tables>
      <tasks>
        - id TEXT PRIMARY KEY (UUID)
        - pipeline_name TEXT NOT NULL
        - status TEXT (queued, running, complete, failed, cancelled)
        - priority INTEGER DEFAULT 0
        - input_path TEXT
        - output_path TEXT
        - current_stage INTEGER DEFAULT 0
        - total_stages INTEGER
        - queued_at, started_at, completed_at DATETIME
        - error_message TEXT
        - metadata TEXT (JSON)
      </tasks>
      <stages>
        - id TEXT PRIMARY KEY
        - task_id TEXT REFERENCES tasks(id)
        - stage_index INTEGER
        - stage_name TEXT
        - skill_name, model, backend TEXT
        - status TEXT (pending, running, complete, failed, skipped)
        - container_id TEXT
        - started_at, completed_at DATETIME
        - iterations INTEGER
        - verification_passed BOOLEAN
        - tokens_used INTEGER
        - duration_seconds REAL
        - error_message TEXT
      </stages>
      <runs>
        - id TEXT PRIMARY KEY
        - stage_id TEXT REFERENCES stages(id)
        - iteration INTEGER
        - action, result TEXT
        - tokens_used INTEGER
        - duration_seconds REAL
        - timestamp DATETIME
      </runs>
    </tables>
  </database_schema>

  <harness_design>
    <state_files>
      - huginn.db: Tasks, stages, runs
      - config.yaml: Endpoints, API keys, limits
      - pipelines/{name}/manifest.yaml: Pipeline definition
      - pipelines/{name}/validation/: Design artifacts
      - tasks/{id}/meta.json: Task status and timing
      - tasks/{id}/stages/{N}/output/checkpoint.json: Agent progress
    </state_files>

    <session_startup_ritual>
      1. Parse manifest, validate stages and wiring
      2. Create task directory with per-stage subdirs
      3. Check for checkpoint (resume if present)
      4. Per stage: check completion, verify model available, create container,
         run agent, validate output, wire to next stage
      5. Collect final output
      6. Update meta.json
    </session_startup_ritual>

    <error_recovery>
      - Stage failure: stop pipeline, preserve partial output, report clearly
      - Ollama unreachable: retry 3x with backoff, then fail
      - Model not loaded: clear message with pull command
      - Container OOM: fail stage, suggest smaller model
      - Checkpoint corruption: restart stage from scratch, warn
      - Timeout: kill container, preserve partial, mark timed_out
      - Never delete partial work
    </error_recovery>
  </harness_design>

</project_specification>
