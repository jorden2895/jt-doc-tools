"""目錄瀏覽（AD/LDAP OU treeview → 指派權限給 OU，2026-07-01）。"""
from __future__ import annotations


def test_directory_page_renders(admin_session):
    c, _, _ = admin_session
    r = c.get("/admin/directory")
    assert r.status_code == 200
    assert "目錄瀏覽" in r.text


def test_directory_endpoints_require_directory_backend(admin_session):
    """local 後端 → 目錄相關端點一律 400（僅 LDAP/AD 可用）。"""
    c, _, _ = admin_session
    assert c.get("/admin/directory/tree").status_code == 400
    assert c.get("/admin/directory/users?dn=OU=x,DC=y").status_code == 400
    assert c.post("/admin/directory/ou-roles",
                  json={"dn": "OU=x,DC=y", "roles": ["clerk"]}).status_code == 400


def test_directory_ldap_functions_exist():
    from app.core import auth_ldap
    assert hasattr(auth_ldap, "list_ou_children")
    assert hasattr(auth_ldap, "list_ou_users")


def test_ou_permission_uses_ou_subject(admin_session):
    """指派給 OU 走 subject_type='ou'（權限模型支援）。"""
    from app.core import permissions
    permissions.set_subject_roles("ou", "OU=Test,DC=example,DC=com", ["clerk"])
    got = permissions.list_roles_for_subject("ou", "OU=Test,DC=example,DC=com")
    assert "clerk" in got
