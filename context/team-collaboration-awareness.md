# Team Collaboration Awareness

Multi-agent teams in Amplifier use the **actor model** — agents communicate by delegating tasks to each other, passing context explicitly, and returning results. There is no shared mutable state between agents. Each agent runs in its own session and communicates through the `delegate()` interface.

## Core Concepts

### Agents as Actors

Each agent is an independent actor with:

- **Its own session** — isolated context, tools, and state.
- **Defined capabilities** — tools and knowledge specified in the agent's bundle definition.
- **A single entry point** — the instruction passed via `delegate()`.
- **A single exit point** — the result message returned when the agent completes.

Agents do not share memory, tool state, or conversation history unless explicitly passed through delegation parameters.

### Communication via Delegation

All inter-agent communication happens through `delegate()`:

```
delegate(
    agent="namespace:agent-name",
    instruction="Clear description of the task",
    context_depth="none" | "recent" | "all",
    context_scope="conversation" | "agents" | "full"
)
```

The delegating agent (coordinator) sends work to a specialist agent and receives a summary result. The specialist's full reasoning stays in its own session — only the final response bubbles up.

## Team Patterns

### Sequential Handoff

Agents work in series, each building on the previous agent's output:

```
Architect → Builder → Reviewer
```

- The coordinator delegates to the architect, receives a design.
- Passes the design to the builder as instruction context.
- Passes the implementation to the reviewer.
- Each agent sees only what the coordinator explicitly passes forward.

**When to use:** Tasks with clear phases where each phase requires different expertise.

### Fan-Out (Parallel)

The coordinator delegates independent subtasks to multiple agents simultaneously:

```
Coordinator → Agent A (research)
            → Agent B (implementation)
            → Agent C (testing)
```

- All agents run concurrently.
- The coordinator collects results and synthesizes.
- Agents are unaware of each other.

**When to use:** Tasks that decompose into independent subtasks with no data dependencies between them.

### Synthesis

Multiple agents analyze the same input from different perspectives, and the coordinator merges their findings:

```
Coordinator → Security Reviewer (risk analysis)
            → Performance Analyst (bottleneck analysis)
            → UX Reviewer (usability analysis)
            ↓
Coordinator synthesizes all perspectives
```

**When to use:** Complex decisions requiring multiple viewpoints. Code review, architecture evaluation, or risk assessment.

## Context Accumulation

The `context_scope` parameter on `delegate()` controls how much prior context the sub-agent receives:

- **`"conversation"`** — Only the text of the conversation (user and assistant messages). Lightest context, fewest tokens.
- **`"agents"`** — Conversation text plus results from prior agent delegations. This is the key setting for team collaboration — it lets downstream agents see what upstream agents produced.
- **`"full"`** — Everything: conversation, agent results, and all tool outputs. Heaviest context. Use sparingly.

### Recommended Pattern for Teams

Use `context_scope="agents"` for agents in a sequential chain. This way each agent sees the results of prior agents without the full tool-call noise:

```python
# Step 1: Architect designs
architect_result = delegate(
    agent="zen-architect",
    instruction="Design caching layer",
    context_scope="conversation"
)

# Step 2: Builder implements — sees architect's output via context_scope="agents"
builder_result = delegate(
    agent="modular-builder",
    instruction="Implement the caching design",
    context_scope="agents"
)

# Step 3: Reviewer reviews — sees both architect and builder output
reviewer_result = delegate(
    agent="code-quality-reviewer",
    instruction="Review the implementation",
    context_scope="agents"
)
```

## Loop Protection and Convergence

Multi-agent workflows can create infinite loops if not carefully designed. Protect against this:

### Loop Protection Strategies

1. **Iteration caps** — Set a maximum number of delegation rounds. After N rounds, the coordinator must produce a final result.
2. **Convergence detection** — Track whether successive iterations are producing meaningfully different results. If two consecutive rounds produce equivalent output, stop.
3. **Diminishing scope** — Each round should address a narrower scope than the previous. If scope is not shrinking, the loop is not converging.
4. **Timeout guards** — Set wall-clock time limits on multi-agent workflows. If the team has not converged in T minutes, force a summary of current state.

### Convergence Pattern

```
Round 1: Agent produces initial result
Round 2: Reviewer identifies issues → Agent addresses them
Round 3: Reviewer identifies fewer issues → Agent addresses them
Round N: Reviewer finds no issues → Converged, stop
```

The coordinator monitors the issue count. If it is not monotonically decreasing, intervene.

## Mapping to Amplifier Recipes

For repeatable team workflows, encode the collaboration pattern as an Amplifier recipe:

### Sequential Team Recipe

```yaml
steps:
  - name: design
    agent: zen-architect
    instruction: "Design the feature based on requirements"

  - name: implement
    agent: modular-builder
    instruction: "Implement the design from the previous step"
    context_from: [design]

  - name: review
    agent: code-quality-reviewer
    instruction: "Review the implementation"
    context_from: [design, implement]
```

### Fan-Out Team Recipe

```yaml
steps:
  - name: analyze
    parallel:
      - agent: security-reviewer
        instruction: "Review for security issues"
      - agent: performance-analyst
        instruction: "Review for performance issues"
      - agent: ux-reviewer
        instruction: "Review for usability issues"

  - name: synthesize
    agent: self
    instruction: "Merge all review findings into a unified report"
    context_from: [analyze]
```

Recipes make team patterns **repeatable, auditable, and resumable**. They also provide built-in checkpointing — if a step fails, the recipe can resume from the last successful step rather than restarting the entire team workflow.

## Best Practices

1. **Explicit over implicit.** Always pass context explicitly through instructions and context parameters. Never assume an agent "knows" what another agent did.
2. **Narrow delegation.** Give each agent a focused task. "Review the authentication module for SQL injection" beats "Review the code."
3. **Coordinator accountability.** The coordinating agent is responsible for synthesis. Sub-agents produce inputs; the coordinator produces the final output.
4. **Minimize context depth.** Use `context_depth="none"` when the instruction contains everything the agent needs. Use `"recent"` for conversational context. Reserve `"all"` for agents that genuinely need full history.
5. **Document team contracts.** If agents are designed to work together, document what each agent expects as input and produces as output. This is the team's API.
