import json
import math
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PIL import Image, UnidentifiedImageError
from flask import Blueprint, current_app, jsonify, redirect, render_template, request, url_for
from sqlalchemy import func, or_
from werkzeug.utils import secure_filename


def create_admin_blueprints(
    db,
    User,
    Game,
    AuditLog,
    Payment,
    GamingSession,
    current_user,
    role_required,
    user_can_manage_branch,
    ALLOWED_BRANCHES,
    money,
):
    admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
    admin_api_bp = Blueprint("admin_api", __name__, url_prefix="/api/admin")

    def _save_game_image(upload, image_kind: str) -> tuple[str | None, str | None]:
        if not upload or not upload.filename:
            return None, None

        original_name = secure_filename(upload.filename)
        extension = Path(original_name).suffix.lower().lstrip(".")
        allowed = current_app.config.get("GAME_ALLOWED_EXTENSIONS", {"jpg", "jpeg", "png", "webp"})
        if extension not in allowed:
            return None, "Images must be JPG, PNG, or WEBP files."

        try:
            upload.stream.seek(0)
            with Image.open(upload.stream) as source:
                source.verify()
            upload.stream.seek(0)
            with Image.open(upload.stream) as source:
                image = source.copy()
                image.thumbnail((1920, 1080), Image.Resampling.LANCZOS)
                output_format = "JPEG" if extension in {"jpg", "jpeg"} else extension.upper()
                if output_format == "JPG":
                    output_format = "JPEG"
                if output_format == "JPEG" and image.mode not in {"RGB", "L"}:
                    image = image.convert("RGB")

                upload_root = Path(current_app.root_path) / current_app.config["GAME_UPLOAD_FOLDER"]
                upload_root.mkdir(parents=True, exist_ok=True)
                filename = f"{uuid4().hex}-{image_kind}.{extension}"
                destination = upload_root / filename
                save_options = {"optimize": True}
                if output_format in {"JPEG", "WEBP"}:
                    save_options["quality"] = 85
                image.save(destination, format=output_format, **save_options)
        except (UnidentifiedImageError, OSError, ValueError):
            return None, "The uploaded file is not a valid image."

        relative_path = Path(current_app.config["GAME_UPLOAD_FOLDER"]) / filename
        return relative_path.as_posix(), None

    def _remove_uploaded_image(image_path: str | None) -> None:
        if not image_path:
            return
        upload_root = (Path(current_app.root_path) / current_app.config["GAME_UPLOAD_FOLDER"]).resolve()
        candidate = (Path(current_app.root_path) / image_path).resolve()
        if candidate.parent == upload_root and candidate.is_file():
            candidate.unlink()

    def _request_ip() -> str | None:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.remote_addr

    def _safe_float_price(raw_value) -> float | None:
        try:
            price = float(raw_value)
        except (TypeError, ValueError):
            return None
        return price if price >= 0 else None

    def _record_game_audit(action: str, game: Game, *, previous_value: dict | None, new_value: dict | None, actor_user_id: int | None = None) -> None:
        db.session.add(
            AuditLog(
                actor_user_id=actor_user_id,
                action=action,
                entity_type="game",
                entity_id=str(game.id),
                metadata_json=json.dumps(
                    {
                        "ip_address": _request_ip(),
                        "previous_value": previous_value or {},
                        "new_value": new_value or {},
                        "game_title": game.title,
                        "game_slug": game.slug,
                    },
                    ensure_ascii=True,
                ),
            )
        )

    def _build_activity_rows(branch: str | None = None) -> list[dict]:
        query = (
            db.session.query(
                GamingSession.id.label("session_id"),
                GamingSession.branch,
                GamingSession.plug_id,
                GamingSession.status,
                User.full_name,
                Payment.amount,
                Payment.status.label("payment_status"),
                GamingSession.created_at,
            )
            .join(User, User.id == GamingSession.user_id)
            .outerjoin(Payment, Payment.id == GamingSession.payment_id)
            .order_by(GamingSession.created_at.desc())
        )
        if branch:
            query = query.filter(GamingSession.branch == branch)

        rows = []
        for item in query.limit(10).all():
            rows.append(
                {
                    "branch": item.branch,
                    "user": item.full_name,
                    "station": item.plug_id,
                    "action": "Session Started" if item.status == "active" else "Session Ended",
                    "target": f"Session #{item.session_id}",
                    "amount": money(item.amount),
                    "status": "Success" if item.payment_status == "successful" else "Review",
                }
            )
        return rows

    @admin_bp.route("/branch1")
    @role_required("admin1", "superadmin")
    def admin1():
        games = Game.query.filter_by(is_active=True, status="active").order_by(Game.display_order.asc(), Game.title.asc()).all()
        return render_template("admin1.html", games=games)

    @admin_bp.route("/branch2")
    @role_required("admin2", "superadmin")
    def admin2():
        games = Game.query.filter_by(is_active=True, status="active").order_by(Game.display_order.asc(), Game.title.asc()).all()
        return render_template("admin2.html", games=games)

    @admin_bp.route("/super")
    @role_required("superadmin")
    def superadmin():
        games = Game.query.order_by(Game.display_order.asc(), Game.title.asc()).all()
        return render_template("superadmin.html", games=games)

    @admin_bp.route("/games", methods=["GET", "POST"])
    @role_required("superadmin")
    def game_management():
        if request.method == "POST":
            title = (request.form.get("title") or "").strip()
            slug = (request.form.get("slug") or "").strip().lower()
            description = (request.form.get("description") or "").strip()
            price = _safe_float_price(request.form.get("price_per_hour"))
            category = (request.form.get("category") or "action").strip().lower()
            console_type = (request.form.get("console_type") or "console").strip().lower()
            status = (request.form.get("status") or "active").strip().lower()
            display_order = int(request.form.get("display_order") or 0)
            cover_image_path = (request.form.get("cover_image_path") or "").strip()
            banner_image_path = (request.form.get("banner_image_path") or "").strip()

            if not title or not slug or price is None:
                return jsonify({"ok": False, "message": "Title, slug, and a valid hourly price are required."}), 400
            if price < 0:
                return jsonify({"ok": False, "message": "Price must be zero or greater."}), 400
            if not status or status not in {"active", "inactive", "archived"}:
                status = "active"
            if not slug:
                slug = title.lower().replace(" ", "-")

            if Game.query.filter(func.lower(Game.title) == func.lower(title)).first():
                return jsonify({"ok": False, "message": "Game name already exists."}), 400
            if Game.query.filter(func.lower(Game.slug) == func.lower(slug)).first():
                return jsonify({"ok": False, "message": "Game slug already exists."}), 400

            user = current_user()
            try:
                uploaded_cover, upload_error = _save_game_image(request.files.get("cover_image"), "cover")
                if upload_error:
                    return jsonify({"ok": False, "message": upload_error}), 400
                uploaded_banner, upload_error = _save_game_image(request.files.get("banner_image"), "banner")
                if upload_error:
                    return jsonify({"ok": False, "message": upload_error}), 400

                cover_image_path = uploaded_cover or cover_image_path
                banner_image_path = uploaded_banner or banner_image_path
                game = Game(
                    title=title,
                    slug=slug,
                    description=description,
                    price_per_hour=price,
                    category=category,
                    console_type=console_type,
                    status=status,
                    display_order=display_order,
                    cover_image_path=cover_image_path or None,
                    banner_image_path=banner_image_path or None,
                    image_path=cover_image_path or None,
                    is_active=status == "active",
                    is_deleted=status == "archived",
                    archived_at=datetime.utcnow() if status == "archived" else None,
                    deleted_at=datetime.utcnow() if status == "archived" else None,
                    created_by=user.id if user else None,
                    updated_by=user.id if user else None,
                )
                db.session.add(game)
                db.session.flush()
                _record_game_audit(
                    "Game Added",
                    game,
                    previous_value=None,
                    new_value={
                        "title": title,
                        "slug": slug,
                        "price_per_hour": float(price),
                        "status": status,
                    },
                    actor_user_id=user.id if user else None,
                )
                db.session.commit()
            except Exception as exc:
                db.session.rollback()
                return jsonify({"ok": False, "message": f"Unable to create game: {exc}"}), 400
            return redirect(url_for("admin.game_management"))

        search = (request.args.get("q") or "").strip()
        status_filter = (request.args.get("status") or "").strip().lower()
        category_filter = (request.args.get("category") or "").strip().lower()
        console_filter = (request.args.get("console_type") or "").strip().lower()
        sort_by = (request.args.get("sort_by") or "display_order").strip().lower()
        sort_dir = (request.args.get("sort_dir") or "asc").strip().lower()
        page = max(int(request.args.get("page") or 1), 1)
        per_page = 10

        query = Game.query
        if search:
            query = query.filter(
                or_(
                    Game.title.ilike(f"%{search}%"),
                    Game.slug.ilike(f"%{search}%"),
                    Game.description.ilike(f"%{search}%"),
                )
            )
        if status_filter:
            query = query.filter(Game.status == status_filter)
        if category_filter:
            query = query.filter(Game.category == category_filter)
        if console_filter:
            query = query.filter(Game.console_type == console_filter)

        if sort_by == "title":
            order = Game.title.asc() if sort_dir == "asc" else Game.title.desc()
        elif sort_by == "price":
            order = Game.price_per_hour.asc() if sort_dir == "asc" else Game.price_per_hour.desc()
        elif sort_by == "status":
            order = Game.status.asc() if sort_dir == "asc" else Game.status.desc()
        elif sort_by == "console":
            order = Game.console_type.asc() if sort_dir == "asc" else Game.console_type.desc()
        else:
            order = Game.display_order.asc() if sort_dir == "asc" else Game.display_order.desc()

        paged_games = query.order_by(order).offset((page - 1) * per_page).limit(per_page).all()
        total_games = query.count()
        total_pages = max(1, math.ceil(total_games / per_page)) if total_games else 1

        categories = [row[0] for row in db.session.query(Game.category).filter(Game.category.isnot(None)).distinct().order_by(Game.category.asc()).all()]
        consoles = [row[0] for row in db.session.query(Game.console_type).filter(Game.console_type.isnot(None)).distinct().order_by(Game.console_type.asc()).all()]

        return render_template(
            "admin_games.html",
            games=paged_games,
            page=page,
            total_pages=total_pages,
            total_games=total_games,
            search=search,
            status_filter=status_filter,
            category_filter=category_filter,
            console_filter=console_filter,
            sort_by=sort_by,
            sort_dir=sort_dir,
            categories=categories,
            consoles=consoles,
        )

    @admin_bp.route("/games/<int:game_id>", methods=["GET", "POST"])
    @role_required("superadmin")
    def game_detail(game_id: int):
        game = Game.query.get_or_404(game_id)
        if request.method == "POST":
            previous_snapshot = {
                "title": game.title,
                "slug": game.slug,
                "description": game.description,
                "price_per_hour": float(game.price_per_hour),
                "category": game.category,
                "console_type": game.console_type,
                "status": game.status,
                "display_order": game.display_order,
                "cover_image_path": game.cover_image_path,
                "banner_image_path": game.banner_image_path,
            }

            title = (request.form.get("title") or game.title).strip()
            slug = (request.form.get("slug") or game.slug).strip().lower()
            if not title:
                return jsonify({"ok": False, "message": "Game name is required."}), 400
            if slug and slug != game.slug and Game.query.filter(func.lower(Game.slug) == func.lower(slug)).first():
                return jsonify({"ok": False, "message": "Game slug already exists."}), 400
            if title and title != game.title and Game.query.filter(func.lower(Game.title) == func.lower(title)).first():
                return jsonify({"ok": False, "message": "Game name already exists."}), 400

            price = _safe_float_price(request.form.get("price_per_hour"))
            if price is None:
                return jsonify({"ok": False, "message": "A valid hourly price is required."}), 400

            try:
                game.title = title
                game.slug = slug or game.slug
                game.description = (request.form.get("description") or game.description).strip()
                game.price_per_hour = price
                game.category = (request.form.get("category") or game.category).strip().lower()
                game.console_type = (request.form.get("console_type") or game.console_type).strip().lower()
                game.status = (request.form.get("status") or game.status).strip().lower()
                game.display_order = int(request.form.get("display_order") or game.display_order)
                game.cover_image_path = (request.form.get("cover_image_path") or game.cover_image_path).strip() or None
                game.banner_image_path = (request.form.get("banner_image_path") or game.banner_image_path).strip() or None
                old_cover = game.cover_image_path
                old_banner = game.banner_image_path
                uploaded_cover, upload_error = _save_game_image(request.files.get("cover_image"), "cover")
                if upload_error:
                    return jsonify({"ok": False, "message": upload_error}), 400
                uploaded_banner, upload_error = _save_game_image(request.files.get("banner_image"), "banner")
                if upload_error:
                    return jsonify({"ok": False, "message": upload_error}), 400
                if uploaded_cover:
                    game.cover_image_path = uploaded_cover
                if uploaded_banner:
                    game.banner_image_path = uploaded_banner
                game.image_path = game.cover_image_path or game.image_path
                game.is_active = game.status == "active"
                game.is_deleted = game.status == "archived"
                if game.status == "archived":
                    game.archived_at = game.archived_at or datetime.utcnow()
                    game.deleted_at = game.deleted_at or datetime.utcnow()
                else:
                    game.archived_at = None
                    game.deleted_at = None
                game.updated_by = current_user().id if current_user() else game.updated_by
                db.session.flush()

                new_snapshot = {
                    "title": game.title,
                    "slug": game.slug,
                    "description": game.description,
                    "price_per_hour": float(game.price_per_hour),
                    "category": game.category,
                    "console_type": game.console_type,
                    "status": game.status,
                    "display_order": game.display_order,
                    "cover_image_path": game.cover_image_path,
                    "banner_image_path": game.banner_image_path,
                }
                if previous_snapshot["price_per_hour"] != new_snapshot["price_per_hour"]:
                    _record_game_audit("Price Changed", game, previous_value={"price_per_hour": previous_snapshot["price_per_hour"]}, new_value={"price_per_hour": new_snapshot["price_per_hour"]}, actor_user_id=current_user().id if current_user() else None)
                if previous_snapshot["status"] != new_snapshot["status"]:
                    _record_game_audit("Status Changed", game, previous_value={"status": previous_snapshot["status"]}, new_value={"status": new_snapshot["status"]}, actor_user_id=current_user().id if current_user() else None)
                if previous_snapshot["title"] != new_snapshot["title"] or previous_snapshot["slug"] != new_snapshot["slug"]:
                    _record_game_audit("Game Edited", game, previous_value={"title": previous_snapshot["title"], "slug": previous_snapshot["slug"]}, new_value={"title": new_snapshot["title"], "slug": new_snapshot["slug"]}, actor_user_id=current_user().id if current_user() else None)
                if uploaded_cover or uploaded_banner or previous_snapshot["cover_image_path"] != new_snapshot["cover_image_path"] or previous_snapshot["banner_image_path"] != new_snapshot["banner_image_path"]:
                    _record_game_audit("Image Changed", game, previous_value={"cover_image_path": previous_snapshot["cover_image_path"], "banner_image_path": previous_snapshot["banner_image_path"]}, new_value={"cover_image_path": new_snapshot["cover_image_path"], "banner_image_path": new_snapshot["banner_image_path"]}, actor_user_id=current_user().id if current_user() else None)
                db.session.commit()
                if uploaded_cover:
                    _remove_uploaded_image(old_cover)
                if uploaded_banner:
                    _remove_uploaded_image(old_banner)
            except Exception as exc:
                db.session.rollback()
                return jsonify({"ok": False, "message": f"Unable to update game: {exc}"}), 400
            return redirect(url_for("admin.game_detail", game_id=game.id))

        return render_template("admin_game_detail.html", game=game)

    @admin_bp.route("/games/<int:game_id>/toggle-status", methods=["POST"])
    @role_required("superadmin")
    def game_toggle_status(game_id: int):
        game = Game.query.get_or_404(game_id)
        if game.status == "archived":
            return redirect(url_for("admin.game_management"))
        next_status = "inactive" if game.status == "active" else "active"
        previous_status = game.status
        try:
            game.status = next_status
            game.is_active = next_status == "active"
            game.is_deleted = False
            game.deleted_at = None
            game.updated_by = current_user().id if current_user() else game.updated_by
            db.session.flush()
            _record_game_audit("Status Changed", game, previous_value={"status": previous_status}, new_value={"status": next_status}, actor_user_id=current_user().id if current_user() else None)
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            return jsonify({"ok": False, "message": f"Unable to update game status: {exc}"}), 400
        return redirect(url_for("admin.game_management"))

    @admin_bp.route("/games/<int:game_id>/soft-delete", methods=["POST"])
    @role_required("superadmin")
    def game_soft_delete(game_id: int):
        game = Game.query.get_or_404(game_id)
        previous_status = game.status
        try:
            game.status = "archived"
            game.is_active = False
            game.is_deleted = True
            game.archived_at = game.archived_at or datetime.utcnow()
            game.deleted_at = game.deleted_at or datetime.utcnow()
            game.updated_by = current_user().id if current_user() else game.updated_by
            db.session.flush()
            _record_game_audit("Game Archived", game, previous_value={"status": previous_status}, new_value={"status": "archived"}, actor_user_id=current_user().id if current_user() else None)
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            return jsonify({"ok": False, "message": f"Unable to archive game: {exc}"}), 400
        return redirect(url_for("admin.game_management"))

    @admin_api_bp.route("/branch/<branch>/summary", methods=["GET"])
    @role_required("admin1", "admin2", "superadmin")
    def api_branch_summary(branch: str):
        user = current_user()
        branch = branch.lower()
        if branch not in ALLOWED_BRANCHES:
            return jsonify({"ok": False, "message": "Invalid branch."}), 400
        if not user_can_manage_branch(user, branch):
            return jsonify({"ok": False, "message": "Forbidden for this branch."}), 403

        active_sessions = GamingSession.query.filter_by(branch=branch, status="active").count()
        declined_payments = Payment.query.filter_by(branch=branch, status="declined").count()
        today_sales = (
            db.session.query(func.coalesce(func.sum(Payment.amount), 0))
            .filter(Payment.branch == branch, Payment.status == "successful")
            .scalar()
        )

        return jsonify(
            {
                "ok": True,
                "branch": branch,
                "metrics": {
                    "active_sessions": active_sessions,
                    "declined_payments": declined_payments,
                    "today_sales": money(today_sales),
                },
                "activities": _build_activity_rows(branch=branch),
            }
        )

    @admin_api_bp.route("/super/summary", methods=["GET"])
    @role_required("superadmin")
    def api_super_summary():
        total_sales = (
            db.session.query(func.coalesce(func.sum(Payment.amount), 0))
            .filter(Payment.status == "successful")
            .scalar()
        )
        active_plugs = GamingSession.query.filter_by(status="active").count()
        online_admins = User.query.filter(User.role.in_(["admin1", "admin2"]), User.is_active.is_(True)).count()
        open_issues = Payment.query.filter_by(status="declined").count()

        return jsonify(
            {
                "ok": True,
                "metrics": {
                    "total_sales": money(total_sales),
                    "active_plugs": active_plugs,
                    "online_admins": online_admins,
                    "open_issues": open_issues,
                },
                "activities": _build_activity_rows(branch=None),
            }
        )

    return admin_bp, admin_api_bp
