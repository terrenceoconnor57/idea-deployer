## idea-deployer

### Project folders
- **Naming**: `idea_gen.py` now assigns a `project_slug` for each new idea (lowercased, hyphenated). This slug becomes the project folder name under `projects/`.
- **Creation/iteration**: `iterate_project.py` ensures a folder `projects/<project_slug>/` exists. If missing, it creates it and initializes a `state.json` seeded from the idea and date. It then writes daily iteration outputs to `projects/<project_slug>/iteration_YYYY-MM-DD/output.md`.

### Files
- **`ideas.json`**: Stores ideas, including `project_slug`.
- **`projects/<slug>/state.json`**: Project metadata and iteration history scaffold.