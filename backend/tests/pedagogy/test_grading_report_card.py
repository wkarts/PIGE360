from __future__ import annotations

from conftest import ALPHA_HOST


def post(env, path: str, payload: dict, *, headers=None, expected: int = 201):
    response = env.client.post(path, headers=headers or env.alpha_headers(), json=payload)
    assert response.status_code == expected, f"{path}: {response.status_code} {response.text}"
    return response.json()


def setup_context(env):
    inst = post(env,"/api/v1/institutions",{"legal_name":"Escola Avaliação Ltda","trade_name":"Escola Avaliação"})
    unit = post(env,"/api/v1/units",{"institution_id":inst["id"],"code":"AVA","name":"Unidade Avaliação","timezone":"America/Bahia"})
    year = post(env,"/api/v1/academic-years",{"institution_id":inst["id"],"name":"2026","starts_on":"2026-01-20","ends_on":"2026-12-18"})
    period = post(env,"/api/v1/academic-periods",{"academic_year_id":year["id"],"name":"3º Bimestre","period_type":"bimester","sequence":3,"starts_on":"2026-07-20","ends_on":"2026-09-30"})
    program = post(env,"/api/v1/programs",{"institution_id":inst["id"],"code":"EF-A","name":"Fundamental II","education_level":"fundamental"})
    curriculum = post(env,"/api/v1/curricula",{"program_id":program["id"],"code":"CURR-A","name":"Currículo Avaliação","effective_from":"2026-01-01"})
    component = post(env,"/api/v1/curriculum-components",{"curriculum_id":curriculum["id"],"code":"MAT-A","name":"Matemática","workload_hours":160})
    group = post(env,"/api/v1/class-groups",{"unit_id":unit["id"],"academic_year_id":year["id"],"program_id":program["id"],"curriculum_id":curriculum["id"],"code":"7A-AVA","name":"7º A","capacity":30})
    teacher_person = post(env,"/api/v1/people",{"full_name":"Professora Avaliação","email":"prof.avaliacao@example.com"},headers=env.alpha_headers(**{"Idempotency-Key":"grading-teacher-person"}))
    employee = post(env,"/api/v1/employees",{"person_id":teacher_person["id"],"employee_number":"PROF-AVA","department":"Pedagógico","position":"Professora","admission_date":"2026-01-10"})
    teacher, token = env.create_alpha_user("prof.grading@alpha.example.com",["teacher"],person_id=teacher_person["id"])
    post(env,"/api/v1/teacher-assignments",{"employee_id":employee["id"],"class_group_id":group["id"],"component_id":component["id"],"starts_on":"2026-01-20","role":"teacher"})
    students=[]
    for index,name in enumerate(("Aluno Nota Sete","Aluno Recuperação"),1):
        person=post(env,"/api/v1/people",{"full_name":name,"cpf":f"1234567890{index}"},headers=env.alpha_headers(**{"Idempotency-Key":f"grading-student-person-{index}"}))
        student=post(env,"/api/v1/students",{"person_id":person["id"],"registration_number":f"AVA-{index:03}"})
        enrollment=post(env,"/api/v1/enrollments",{"student_id":student["id"],"institution_id":inst["id"],"unit_id":unit["id"],"program_id":program["id"],"curriculum_id":curriculum["id"],"academic_year_id":year["id"],"class_group_id":group["id"],"enrollment_number":f"MAT-AVA-{index:03}"},headers=env.alpha_headers(**{"Idempotency-Key":f"grading-enrollment-{index}"}))
        activated=post(env,f"/api/v1/enrollments/{enrollment['id']}/activate",{"expected_version":1,"reason":"Matrícula ativa para avaliação"},expected=200)
        assert activated["state"]=="active"
        students.append((student,enrollment,person))
    return {"inst":inst,"unit":unit,"year":year,"period":period,"program":program,"curriculum":curriculum,"component":component,"group":group,"teacher":teacher,"token":token,"students":students}


def test_assessments_grades_recovery_close_reopen_and_report_card(local_env):
    ctx=setup_context(local_env)
    policy=post(local_env,"/api/v1/pedagogy/grading-policies",{
        "academic_year_id":ctx["year"]["id"],"class_group_id":ctx["group"]["id"],"component_id":ctx["component"]["id"],
        "name":"Média bimestral 0-10","max_score":"10","passing_score":"6","attendance_minimum":"75","rounding_precision":2,
        "recovery_strategy":"replace_if_higher","missing_score_strategy":"zero","effective_from":"2026-01-20"
    })
    teacher_headers=local_env.headers(ALPHA_HOST,ctx["token"])
    assessments=[]
    for idx,title in enumerate(("Prova 1","Trabalho 1"),1):
        assessment=post(local_env,"/api/v1/pedagogy/assessments",{
            "academic_period_id":ctx["period"]["id"],"class_group_id":ctx["group"]["id"],"component_id":ctx["component"]["id"],
            "grading_policy_id":policy["id"],"title":title,"assessment_type":"exam" if idx==1 else "work","weight":"1","max_score":"10","due_on":f"2026-08-{10+idx:02}"
        },headers=teacher_headers)
        published=post(local_env,f"/api/v1/pedagogy/assessments/{assessment['id']}/publish",{"expected_version":1,"reason":"Avaliação liberada para lançamento"},headers=teacher_headers,expected=200)
        assert published["state"]=="published"
        assessments.append(assessment)

    scores=(("8","4"),("6","4"))
    for assessment, pair in zip(assessments,scores):
        saved=local_env.client.put(f"/api/v1/pedagogy/assessments/{assessment['id']}/grades",headers=teacher_headers,json={"reason":"Correção concluída","grades":[
            {"enrollment_id":ctx["students"][0][1]["id"],"score":pair[0],"status":"graded","feedback":"Bom desempenho"},
            {"enrollment_id":ctx["students"][1][1]["id"],"score":pair[1],"status":"graded","feedback":"Requer recuperação"}
        ]})
        assert saved.status_code==200,saved.text
        assert len(saved.json()["items"])==2

    calculated=post(local_env,"/api/v1/pedagogy/period-results/calculate",{
        "academic_period_id":ctx["period"]["id"],"class_group_id":ctx["group"]["id"],"component_id":ctx["component"]["id"]
    },headers=teacher_headers,expected=200)
    by_enrollment={x["enrollment_id"]:x for x in calculated["items"]}
    first=by_enrollment[ctx["students"][0][1]["id"]]; second=by_enrollment[ctx["students"][1][1]["id"]]
    assert first["average_score"]=="7.00" and first["final_score"]=="7.00" and first["outcome"]=="approved"
    assert first["attendance_percentage"]=="100.00"
    assert second["average_score"]=="4.00" and second["outcome"]=="recovery"

    recovered=post(local_env,f"/api/v1/pedagogy/period-results/{second['id']}/recovery",{"score":"7","reason":"Recuperação bimestral","expected_version":second["version"]},headers=teacher_headers,expected=200)
    assert recovered["final_score"]=="7.00" and recovered["outcome"]=="approved"

    closed=post(local_env,"/api/v1/pedagogy/grade-periods/close",{"academic_period_id":ctx["period"]["id"],"class_group_id":ctx["group"]["id"],"component_id":ctx["component"]["id"],"reason":"Conselho bimestral concluído"},expected=200)
    assert closed["state"]=="closed" and closed["results"]==2
    denied=local_env.client.put(f"/api/v1/pedagogy/assessments/{assessments[0]['id']}/grades",headers=teacher_headers,json={"reason":"Tentativa após fechamento","grades":[{"enrollment_id":ctx["students"][0][1]["id"],"score":"9","status":"graded","expected_version":1}]})
    assert denied.status_code==409

    reopened=post(local_env,"/api/v1/pedagogy/grade-periods/reopen",{"academic_period_id":ctx["period"]["id"],"class_group_id":ctx["group"]["id"],"component_id":ctx["component"]["id"],"reason":"Correção autorizada pela coordenação"},expected=200)
    assert reopened["state"]=="reopened"
    detail=local_env.client.get(f"/api/v1/pedagogy/assessments/{assessments[0]['id']}",headers=teacher_headers)
    assert detail.status_code==200,detail.text
    grade=next(x for x in detail.json()["grades"] if x["enrollment_id"]==ctx["students"][0][1]["id"])
    corrected=local_env.client.put(f"/api/v1/pedagogy/assessments/{assessments[0]['id']}/grades",headers=teacher_headers,json={"reason":"Revisão de correção","grades":[{"enrollment_id":ctx["students"][0][1]["id"],"score":"9","status":"graded","feedback":"Nota revisada","expected_version":grade["version"]}]})
    assert corrected.status_code==200,corrected.text

    recalculated=post(local_env,"/api/v1/pedagogy/period-results/calculate",{"academic_period_id":ctx["period"]["id"],"class_group_id":ctx["group"]["id"],"component_id":ctx["component"]["id"],"enrollment_ids":[ctx["students"][0][1]["id"]]},headers=teacher_headers,expected=200)
    assert recalculated["items"][0]["average_score"]=="7.50"

    report=local_env.client.get(f"/api/v1/pedagogy/students/{ctx['students'][0][0]['id']}/report-card",headers=local_env.alpha_headers())
    assert report.status_code==200,report.text
    results=report.json()["enrollments"][0]["results"]
    assert any(x["component_name"]=="Matemática" and float(x["final_score"])==7.5 for x in results)


def test_teacher_cannot_grade_other_class(local_env):
    owner=setup_context(local_env)
    # Cria outra turma no mesmo escopo curricular sem atribuir a professora autenticada.
    other_group=post(local_env,"/api/v1/class-groups",{"unit_id":owner["unit"]["id"],"academic_year_id":owner["year"]["id"],"program_id":owner["program"]["id"],"curriculum_id":owner["curriculum"]["id"],"code":"8B-AVA","name":"8º B","capacity":30})
    teacher_headers=local_env.headers(ALPHA_HOST,owner["token"])
    denied=local_env.client.post("/api/v1/pedagogy/assessments",headers=teacher_headers,json={"academic_period_id":owner["period"]["id"],"class_group_id":other_group["id"],"component_id":owner["component"]["id"],"title":"Avaliação indevida","weight":"1","max_score":"10"})
    assert denied.status_code==403,denied.text
    assert denied.json()["code"]=="TEACHER_NOT_ASSIGNED"
