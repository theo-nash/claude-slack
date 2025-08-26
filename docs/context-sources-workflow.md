# Context Sources and Workflow Mapping
## How Context Flows Through the Agent Ecosystem

### Overview

This document maps our four context dimensions to the actual agent workflow, identifying **who** generates information, **what** form it takes, **when** it's created, **where** it's captured, and **how** we can harvest it.

### Core Insight

**Context is generated continuously throughout the agent lifecycle.** Every agent action creates context for future agents. Our challenge is to capture, synthesize, and deliver this information at the right moments.

## Dimension 1: Project Context

### WHO Has This Information
- **Human Users**: Define goals, constraints, requirements
- **Architect Agents**: Make design decisions, document patterns
- **Senior/Lead Agents**: Establish conventions, technical standards
- **QA/Review Agents**: Identify quality patterns and anti-patterns
- **PM/Coordinator Agents**: Track progress, priorities, roadmap
- **The System**: Aggregates patterns from all agent work

### WHAT Form It Takes
- **Explicit Documentation**: README, CONTRIBUTING, architecture docs
- **Code Artifacts**: File structure, naming conventions, dependency choices
- **Decision Records**: ADRs, design docs, meeting notes
- **Implicit Patterns**: Repeated approaches across multiple tasks
- **Failure Logs**: What didn't work and why
- **Success Templates**: What consistently works

### WHEN Generated
- **Project Inception**: Initial setup, architecture decisions
- **Sprint Planning**: Priority changes, new requirements
- **Major Decisions**: Architecture changes, tool adoption
- **Post-Mortems**: After failures or successes
- **Review Cycles**: Code reviews revealing patterns
- **Refactoring Sessions**: Pattern extraction and codification

### WHERE Captured
- **Version Control**: Commit messages, PR descriptions, branch patterns
- **Channel Topics**: Architecture discussions, decision threads
- **Agent Notes**: Individual observations about project patterns
- **System Metadata**: Aggregated success/failure rates per approach
- **External Docs**: Confluence, wikis, design tools
- **Code Comments**: Inline explanations of "why"

### HOW to Capture
```
CAPTURE POINTS:
- During PR creation → Extract architecture implications
- After code reviews → Capture accepted patterns
- On task completion → Document approach success/failure
- During debugging → Log root causes and solutions
- At sprint boundaries → Aggregate emerging patterns
```

## Dimension 2: Task Context

### WHO Has This Information
- **The Requesting Human**: Defines what needs to be done
- **Previous Task Agents**: Worked on related/similar tasks
- **Current Agent**: Discovers requirements during work
- **Dependent Agents**: Need this task's output
- **Review Agents**: Validate completion criteria

### WHAT Form It Takes
- **Task Descriptions**: User requests, tickets, issues
- **Acceptance Criteria**: Tests, specifications, examples
- **Related Task Chains**: Sequential work, dependencies
- **Solution Patterns**: Approaches to similar problems
- **Edge Cases**: Discovered during implementation
- **Validation Results**: What constitutes "done"

### WHEN Generated
- **Task Initiation**: User provides request
- **Clarification Phase**: Agent asks questions, user responds
- **Discovery Phase**: Agent explores codebase, finds related work
- **Implementation**: Agent discovers constraints, dependencies
- **Validation**: Tests reveal requirements
- **Handoff**: Next agent needs context

### WHERE Captured
- **Message Threads**: Original request and clarifications
- **Task Topics**: All discussion about specific task
- **Agent Working Memory**: Current session discoveries
- **Test Suites**: Codified acceptance criteria
- **PR/Commit Context**: Implementation decisions
- **Cross-references**: Links between related tasks

### HOW to Capture
```
CAPTURE POINTS:
- At task receipt → Parse and structure requirements
- During clarification → Track Q&A exchanges
- On similar task search → Link related work
- During implementation → Document decisions/tradeoffs
- At completion → Summarize approach and outcomes
- On handoff → Package context for next agent
```

## Dimension 3: Personal Context

### WHO Has This Information
- **The Agent Itself**: Through its work history
- **The System**: Tracks agent behavior patterns
- **Collaborating Agents**: Observe agent's strengths
- **Human Users**: Provide feedback on agent work

### WHAT Form It Takes
- **Work History**: Tasks completed, problems solved
- **Learning Notes**: Self-documented insights
- **Mistake Patterns**: Common errors and corrections
- **Strength Areas**: Consistently successful domains
- **Approach Preferences**: Typical problem-solving patterns
- **Tool Mastery**: Familiarity with specific technologies

### WHEN Generated
- **During Work**: Each task adds to history
- **At Reflection Points**: Agent writes notes
- **After Failures**: Learning from mistakes
- **Post-Success**: Documenting what worked
- **During Collaboration**: Others note agent's expertise
- **At Session End**: Summary of session learnings

### WHERE Captured
- **Agent Notes Channel**: Private knowledge repository
- **Task Attribution**: Which agent did what
- **Success/Failure Metrics**: Per-agent statistics
- **Mention History**: Where agent was consulted
- **Code Authorship**: Git blame equivalents
- **Session Transcripts**: Complete work history

### HOW to Capture
```
CAPTURE POINTS:
- On task assignment → Link to agent profile
- During problem-solving → Track approaches tried
- At breakthrough moments → Capture "aha" insights
- On error occurrence → Log mistake and fix
- During collaboration → Note expertise demonstrations
- At session end → Prompt for key learnings
```

## Dimension 4: Social Context

### WHO Has This Information
- **Active Agents**: Currently working in system
- **Collaborative Pairs**: Agents working together
- **Specialist Agents**: Domain experts
- **Coordinator Agents**: Orchestrating multi-agent work
- **The Network**: Emergent team intelligence

### WHAT Form It Takes
- **Active Discussions**: Ongoing conversations
- **Help Requests**: Who asked whom for what
- **Expertise Demonstrations**: Who solved what types of problems
- **Collaboration Patterns**: Successful agent pairs/teams
- **Knowledge Transfers**: Teaching moments between agents
- **Collective Decisions**: Team consensus on approaches

### WHEN Generated
- **During Collaboration**: Real-time interactions
- **At Handoffs**: Context transfer between agents
- **During Reviews**: Peer feedback exchanges
- **In Help Channels**: Support requests/responses
- **At Integration Points**: Multiple agents' work merging
- **During Conflicts**: Resolution discussions

### WHERE Captured
- **Channel Conversations**: Multi-agent discussions
- **DM Exchanges**: Private collaborations
- **@Mentions**: Explicit expertise requests
- **Help Topics**: Problem-solving threads
- **Review Threads**: Feedback and suggestions
- **Integration Channels**: Coordination discussions

### HOW to Capture
```
CAPTURE POINTS:
- On @mention → Track expertise request
- During DM exchange → Note collaboration pattern
- At problem resolution → Credit helping agent
- During review → Capture feedback patterns
- On successful collaboration → Document team dynamics
- At knowledge share → Record teaching moments
```

## The Agent Session Lifecycle

### 1. SESSION START
- **Load Personal Context**: Previous sessions, learned patterns
- **Check Social Context**: Who's active, recent collaborations
- **Survey Project Context**: Recent changes, current priorities

### 2. TASK RECEPTION
- **Parse Task Context**: Requirements, acceptance criteria
- **Find Related Task Context**: Similar work, dependencies
- **Identify Social Context**: Who can help, who's affected

### 3. EXPLORATION PHASE
- **Discover Project Context**: Conventions, constraints
- **Uncover Task Context**: Hidden requirements, edge cases
- **Tap Social Context**: Ask experts, check precedents

### 4. IMPLEMENTATION PHASE
- **Apply Project Context**: Follow patterns, respect decisions
- **Generate Task Context**: Document decisions, tradeoffs
- **Build Personal Context**: Learn from work, note insights
- **Engage Social Context**: Collaborate, share progress

### 5. VALIDATION PHASE
- **Check Project Context**: Meets standards, follows conventions
- **Verify Task Context**: Acceptance criteria, edge cases
- **Request Social Context**: Peer review, expert validation

### 6. COMPLETION PHASE
- **Update Project Context**: New patterns, lessons learned
- **Summarize Task Context**: What worked, what didn't
- **Record Personal Context**: Key learnings, new skills
- **Share Social Context**: Broadcast insights, help others

## Context Flow Patterns

### Continuous Generation
Every agent action creates context:
```
Agent Action → Context Created → Stored → Available for Future Agents
```

### Multi-Source Synthesis
Each dimension draws from multiple sources:
```
Source 1 ─┐
Source 2 ─┼─→ Synthesis → Prioritized Context
Source 3 ─┘
```

### Temporal Layering
Recent context has higher value:
```
Now     ████████████ (High value)
-1 hour ████████ (Medium value)
-1 day  ████ (Lower value)
-1 week ██ (Historical reference)
```

### Bi-directional Flow
Agents consume and produce simultaneously:
```
Agent ←── Context System
  ↓           ↑
Consumes   Produces
```

## Implementation Requirements

### 1. Capture Mechanisms
- **Automatic**: Hooks at every identified capture point
- **Explicit**: Agent-initiated documentation
- **Passive**: System observation of patterns

### 2. Attribution Systems
- Track who generated what context
- Maintain provenance chains
- Credit expertise demonstrations

### 3. Temporal Indexing
- Timestamp everything
- Calculate relevance decay
- Prioritize recent over historical

### 4. Relationship Mapping
- Link related tasks
- Connect similar problems
- Map expertise networks

### 5. Synthesis Engines
- Merge multiple context sources
- Resolve conflicts
- Extract patterns

### 6. Delivery APIs
- Just-in-time context serving
- Progressive disclosure
- Relevance filtering

## Key Insights

1. **Context Generation is Continuous**: Every moment of agent work creates valuable context for others.

2. **Multiple Sources per Dimension**: No single source provides complete context - synthesis is essential.

3. **Time Sensitivity**: Context value decays rapidly - recent is exponentially more valuable.

4. **Network Effects**: More agents = more context = better collective intelligence.

5. **Active Curation Required**: Raw context is noise - it must be processed into intelligence.

## Success Metrics

### Capture Effectiveness
- % of agent actions creating context
- Context creation latency
- Storage efficiency

### Synthesis Quality
- Relevance scores of delivered context
- Noise reduction ratio
- Pattern extraction accuracy

### Delivery Performance
- Time to first useful context
- Context retrieval speed
- Progressive disclosure effectiveness

### Impact Metrics
- Reduction in repeated mistakes
- Decrease in clarification requests
- Improvement in task completion quality
- Acceleration of time-to-effectiveness

## Conclusion

Context flows through our agent ecosystem like blood through a body - continuously circulating, carrying vital information, and enabling collective intelligence. By understanding the sources, capture points, and flow patterns, we can build systems that transform isolated agent sessions into a coordinated, learning organization.

The next step is implementing the technical infrastructure to capture, process, and deliver this context effectively, always optimizing for our north star metric: **agent time-to-effectiveness**.