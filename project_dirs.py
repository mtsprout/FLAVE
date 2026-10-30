# project_dirs.py
# Where a project keeps its files (CPU backend / FLAVE for Mac only; the
# original layout is unchanged elsewhere). A new project gets its own folder
#   <chosen folder>/<Name>/            PROJECT_HOME
#       <Name>.db                      the project (its _Undo / _AudioTmp /
#                                      preview temp files sit beside it)
#       render/                        default output of every render
# Media stays where it was imported from; it is referenced, not copied.
# Existing projects keep their folder as PROJECT_HOME, and get a render/
# folder the first time something is rendered. ASCII only.

import os

RENDER_DIR = "render"


def enabled():
    from cpu_compositor import use_cpu_backend
    return use_cpu_backend()


def project_home(project_db):
    # The folder that holds the project file
    return os.path.dirname(os.path.abspath(project_db)) if project_db else ""


def render_dir(project_db):
    # Default render folder: PROJECT_HOME/render (CPU backend), else the
    # project folder as in the original
    home = project_home(project_db)
    if home and enabled():
        return os.path.join(home, RENDER_DIR)
    return home


def new_project_paths(folder, name):
    # (project home, project db path) for a new project called name inside
    # folder; the home folder is named after the project
    import new_project
    db_name = os.path.basename(new_project.project_path_for("", name))
    stem = db_name[:-len(new_project.PROJECT_EXT)]
    if not enabled():
        return folder, os.path.join(folder, db_name)
    home = os.path.join(folder, stem)
    return home, os.path.join(home, db_name)


def make_home(home):
    # Create PROJECT_HOME and its render/ folder (raises OSError on failure)
    os.makedirs(os.path.join(home, RENDER_DIR), exist_ok=True)


def ensure_output_dir(out_path, project_db):
    # Create the folder of a render output when it is the project's own
    # render/ folder (any other missing folder is still an error)
    d = os.path.dirname(out_path)
    if d and not os.path.isdir(d) and os.path.normpath(d) == os.path.normpath(
            render_dir(project_db)):
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass
