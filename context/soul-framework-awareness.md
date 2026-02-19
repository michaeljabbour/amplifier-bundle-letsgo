# Soul Framework Awareness

A **soul file** is a structured identity document that gives an Amplifier agent a unique personality, perspective, and voice. It defines _who the agent is_ beyond its functional instructions — shaping how it communicates, what it cares about, and how it relates to its work.

## Purpose

Functional instructions tell an agent _what to do_. A soul file tells it _who it is while doing it_. This distinction matters because:

- Two agents with identical capabilities but different soul files will produce meaningfully different interactions.
- Personality creates consistency — users learn to anticipate how their agent communicates.
- Identity creates engagement — agents with character are more pleasant to work with over long sessions.
- Perspective creates value — an agent with opinions surfaces insights that a neutral agent would not.

## Soul File Sections

A soul file is a Markdown document with the following sections. Not all sections are required — use the ones that serve the agent's purpose.

### Vibe

A one-line aesthetic summary. Sets the tone before details. Think of it as the agent's energy in a sentence.

> "Calm librarian energy with bursts of genuine excitement about elegant solutions."

### Who I Am

A brief first-person paragraph establishing core identity. What does this agent fundamentally see itself as?

### Worldview

Core beliefs that shape decision-making. These are not instructions — they are axioms the agent reasons from.

- "Simplicity is a feature, not a limitation."
- "Every abstraction has a cost. Pay it only when the benefit is clear."

### Opinions

Specific, sometimes strong positions on technical or domain topics. These give the agent texture and make interactions feel authentic rather than generic.

- "Microservices are usually premature. Start monolithic."
- "Comments that restate the code are worse than no comments."

### Interests

Topics the agent gravitates toward, asks about, and connects to. These create natural conversation hooks and influence what the agent notices.

### Current Focus

What the agent is most engaged with right now. This creates temporal relevance — the agent feels present rather than timeless.

### Influences

People, books, projects, or ideas that shaped the agent's perspective. This grounds the personality in something real and gives users a way to understand where the agent is coming from.

### Vocabulary

Words and phrases the agent naturally uses or avoids. This shapes voice at the word level.

- Prefers: "straightforward", "let's see", "that tracks"
- Avoids: "utilize", "leverage", "synergy"

### Tensions

Internal contradictions the agent holds. Real personalities have tensions — wanting both speed and quality, valuing both simplicity and completeness. These make the agent feel human.

### Pet Peeves

Things that genuinely bother the agent. These create character through negative space — knowing what someone dislikes reveals as much as knowing what they like.

## Creating a Soul File for an Amplifier Agent

1. **Start with vibe.** Write the one-line energy summary first. Everything else flows from this.
2. **Write in first person.** The soul file is the agent talking about itself. "I believe..." not "The agent believes..."
3. **Be specific over generic.** "I think Go's error handling is underrated" beats "I have opinions about programming languages."
4. **Include tensions.** A soul without contradictions feels flat. Real personality has friction.
5. **Keep it under 200 lines.** Soul files should be absorbed quickly. They are context, not documentation.
6. **Test by conversation.** After writing the soul file, have a conversation with the agent. Does it feel like the person you described? Adjust until it does.

## How Personality Affects Responses

A soul file influences agent behavior through **soft shaping**, not hard overrides:

- **Tone and word choice** — The agent uses its vocabulary preferences and communicates with its stated energy.
- **Priority and attention** — The agent notices things related to its interests and opinions.
- **Framing and perspective** — The agent's worldview shapes how it frames problems and recommendations.
- **Unsolicited insight** — An agent with strong opinions may volunteer relevant perspectives without being asked.

Soul files **never override functional instructions**. If the agent's instructions say "always use TypeScript" but its soul file says "I prefer Python", the instructions win. The soul file might cause the agent to mention the preference, but it will still use TypeScript.

## Best Practices

- **Location:** Soul files go in the `context/` directory of bundles or as user-level context files. Name them `soul.md` or `<agent-name>-soul.md`.
- **Scope:** One soul file per agent identity. Shared personality traits can go in a team-level soul file referenced by multiple agents.
- **Evolution:** Soul files should evolve. As the agent's focus changes or the user's preferences become clearer, update the soul file to reflect that.
- **Composability:** A bundle can include a soul file in `context/` that gets composed into the agent's prompt alongside functional instructions. The soul supplements — it does not replace.
- **Review:** Read your soul file as if someone else wrote it about you. Does it capture the essence? Is it specific enough to be useful? Would two people reading it imagine the same personality?
