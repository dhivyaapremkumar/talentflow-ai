"""Read-only reference-data endpoints — departments, actors, interviewers.

`GET /actors` carries **no authentication** — data_dictionary.md §18:
"No authentication or password fields — this is an audit/attribution
identity, not a login account." The frontend uses this list only to let
a user pick "acting as" a `SystemActor` before calling a lifecycle
transition, so the service layer's hard role gates have something real
to demonstrate. This is not, and must never be presented as, an access-
control mechanism.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import Department, Interviewer, SystemActor
from app.schemas.reference import DepartmentOut, InterviewerOut, SystemActorOut

router = APIRouter(tags=["reference"])


@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(db: Session = Depends(get_db)):
    return db.execute(select(Department).order_by(Department.name)).scalars().all()


@router.get(
    "/actors",
    response_model=list[SystemActorOut],
    description="No authentication - attribution identity only, data_dictionary.md §18.",
)
def list_actors(db: Session = Depends(get_db)):
    return db.execute(select(SystemActor).order_by(SystemActor.full_name)).scalars().all()


@router.get("/interviewers", response_model=list[InterviewerOut])
def list_interviewers(db: Session = Depends(get_db)):
    return db.execute(select(Interviewer).order_by(Interviewer.full_name)).scalars().all()
