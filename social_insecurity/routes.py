"""Provides all routes for the Social Insecurity application.

This file contains the routes for the application. It is imported by the social_insecurity package.
It also contains the SQL queries used for communicating with the database.
"""

from pathlib import Path

from flask import current_app as app
from flask import flash, redirect, render_template, send_from_directory, url_for

from social_insecurity import sqlite
from social_insecurity.forms import CommentsForm, FriendsForm, IndexForm, PostForm, ProfileForm


@app.route("/", methods=["GET", "POST"])
@app.route("/index", methods=["GET", "POST"])
def index():
    """Provides the index page for the application.

    It reads the composite IndexForm and based on which form was submitted,
    it either logs the user in or registers a new user.

    If no form was submitted, it simply renders the index page.
    """
    index_form = IndexForm()
    login_form = index_form.login
    register_form = index_form.register

    # Use validate_on_submit to ensure WTForms validators run server-side
    if login_form.validate_on_submit() and login_form.submit.data:
        get_user = f"""
            SELECT *
            FROM Users
            WHERE username = '{login_form.username.data}';
            """
        user = sqlite.query(get_user, one=True)

        if user is None:
            flash("Sorry, this user does not exist!", category="warning")
        elif user["password"] != login_form.password.data:
            flash("Sorry, wrong password!", category="warning")
        elif user["password"] == login_form.password.data:
            return redirect(url_for("stream", username=login_form.username.data))

    elif register_form.validate_on_submit() and register_form.submit.data:
        # All validators passed, safe to insert
        insert_user = f"""
            INSERT INTO Users (username, first_name, last_name, password)
            VALUES ('{register_form.username.data}', '{register_form.first_name.data}', '{register_form.last_name.data}', '{register_form.password.data}');
            """
        sqlite.query(insert_user)
        flash("User successfully created!", category="success")
        return redirect(url_for("index"))
    elif register_form.is_submitted() and register_form.submit.data:
        # Form was submitted but validation failed — collect and flash errors
        for field_name, field_errors in register_form.errors.items():
            for error in field_errors:
                flash(f"{getattr(register_form, field_name).label.text}: {error}", category="warning")

    return render_template("index.html.j2", title="Welcome", form=index_form)


@app.route("/stream/<string:username>", methods=["GET", "POST"])
def stream(username: str):
    """Provides the stream page for the application.

    If a form was submitted, it reads the form data and inserts a new post into the database.

    Otherwise, it reads the username from the URL and displays all posts from the user and their friends.
    """
    post_form = PostForm()
    get_user = f"""
        SELECT *
        FROM Users
        WHERE username = '{username}';
        """
    user = sqlite.query(get_user, one=True)

    if post_form.is_submitted():
        if post_form.image.data:
            path = Path(app.instance_path) / app.config["UPLOADS_FOLDER_PATH"] / post_form.image.data.filename
            post_form.image.data.save(path)

        insert_post = f"""
            INSERT INTO Posts (u_id, content, image, creation_time)
            VALUES ({user["id"]}, '{post_form.content.data}', '{post_form.image.data.filename}', CURRENT_TIMESTAMP);
            """
        sqlite.query(insert_post)
        return redirect(url_for("stream", username=username))

    get_posts = f"""
         SELECT p.*, u.*, (SELECT COUNT(*) FROM Comments WHERE p_id = p.id) AS cc
         FROM Posts AS p JOIN Users AS u ON u.id = p.u_id
         WHERE p.u_id IN (SELECT u_id FROM Friends WHERE f_id = {user["id"]}) OR p.u_id IN (SELECT f_id FROM Friends WHERE u_id = {user["id"]}) OR p.u_id = {user["id"]}
         ORDER BY p.creation_time DESC;
        """
    posts = sqlite.query(get_posts)
    return render_template("stream.html.j2", title="Stream", username=username, form=post_form, posts=posts)


@app.route("/comments/<string:username>/<int:post_id>", methods=["GET", "POST"])
def comments(username: str, post_id: int):
    """Provides the comments page for the application.

    If a form was submitted, it reads the form data and inserts a new comment into the database.

    Otherwise, it reads the username and post id from the URL and displays all comments for the post.
    """
    comments_form = CommentsForm()
    get_user = f"""
        SELECT *
        FROM Users
        WHERE username = '{username}';
        """
    user = sqlite.query(get_user, one=True)

    if comments_form.is_submitted():
        insert_comment = f"""
            INSERT INTO Comments (p_id, u_id, comment, creation_time)
            VALUES ({post_id}, {user["id"]}, '{comments_form.comment.data}', CURRENT_TIMESTAMP);
            """
        sqlite.query(insert_comment)

    get_post = f"""
        SELECT *
        FROM Posts AS p JOIN Users AS u ON p.u_id = u.id
        WHERE p.id = {post_id};
        """
    get_comments = f"""
        SELECT DISTINCT *
        FROM Comments AS c JOIN Users AS u ON c.u_id = u.id
        WHERE c.p_id={post_id}
        ORDER BY c.creation_time DESC;
        """
    post = sqlite.query(get_post, one=True)
    comments = sqlite.query(get_comments)
    return render_template(
        "comments.html.j2", title="Comments", username=username, form=comments_form, post=post, comments=comments
    )


@app.route("/friends/<string:username>", methods=["GET", "POST"])
def friends(username: str):
    """Provides the friends page for the application.

    If a form was submitted, it reads the form data and inserts a new friend into the database.

    Otherwise, it reads the username from the URL and displays all friends of the user.
    """
    friends_form = FriendsForm()
    get_user = f"""
        SELECT *
        FROM Users
        WHERE username = '{username}';
        """
    user = sqlite.query(get_user, one=True)

    if friends_form.is_submitted():
        get_friend = f"""
            SELECT *
            FROM Users
            WHERE username = '{friends_form.username.data}';
            """
        friend = sqlite.query(get_friend, one=True)
        get_friends = f"""
            SELECT f_id
            FROM Friends
            WHERE u_id = {user["id"]};
            """
        friends = sqlite.query(get_friends)

        if friend is None:
            flash("User does not exist!", category="warning")
        elif friend["id"] == user["id"]:
            flash("You cannot be friends with yourself!", category="warning")
        elif friend["id"] in [friend["f_id"] for friend in friends]:
            flash("You are already friends with this user!", category="warning")
        else:
            insert_friend = f"""
                INSERT INTO Friends (u_id, f_id)
                VALUES ({user["id"]}, {friend["id"]});
                """
            sqlite.query(insert_friend)
            flash("Friend successfully added!", category="success")

    get_friends = f"""
        SELECT *
        FROM Friends AS f JOIN Users as u ON f.f_id = u.id
        WHERE f.u_id = {user["id"]} AND f.f_id != {user["id"]};
        """
    friends = sqlite.query(get_friends)

    # People who added me (followers)
    get_followers = f"""
        SELECT *
        FROM Friends AS f JOIN Users as u ON f.u_id = u.id
        WHERE f.f_id = {user["id"]};
        """
    followers = sqlite.query(get_followers)

    # Mark mutual status for followers (did I add them back?) and keep only non-mutual followers
    friend_ids = {f['id'] for f in (friends or [])}
    non_mutual_followers = []
    for fol in (followers or []):
        fol = dict(fol)
        mutual = fol.get('id') in friend_ids
        if not mutual:
            non_mutual_followers.append(fol)

    return render_template("friends.html.j2", title="Friends", username=username, friends=friends, followers=non_mutual_followers, form=friends_form)


@app.route("/profile/<string:viewer>/<string:username>", methods=["GET", "POST"])
def profile(viewer: str, username: str):
    """Provides the profile page for the application.

    If a form was submitted, it reads the form data and updates the user's profile in the database.

    Otherwise, it reads the username from the URL and displays the user's profile.
    """
    profile_form = ProfileForm()
    # viewer: who is requesting the page, username: whose profile is being viewed
    get_owner = f"""
        SELECT *
        FROM Users
        WHERE username = '{username}';
        """
    owner = sqlite.query(get_owner, one=True)

    get_viewer = f"""
        SELECT *
        FROM Users
        WHERE username = '{viewer}';
        """
    viewer_user = sqlite.query(get_viewer, one=True)

    # If someone else is viewing the profile and they have previously added the owner,
    # require that the owner has added them back (mutual) before allowing access.
    if viewer != username and viewer_user is not None and owner is not None:
        # Check if viewer added owner
        viewer_added_owner = sqlite.query(f"SELECT * FROM Friends WHERE u_id = {viewer_user['id']} AND f_id = {owner['id']};", one=True)
        # Check if owner added viewer
        owner_added_viewer = sqlite.query(f"SELECT * FROM Friends WHERE u_id = {owner['id']} AND f_id = {viewer_user['id']};", one=True)

        if viewer_added_owner and not owner_added_viewer:
            flash("You cannot view this profile until they add you back.", category="warning")
            return redirect(url_for("stream", username=viewer))

    # Only owner may update their profile
    if viewer == username and profile_form.is_submitted():
        update_profile = f"""
            UPDATE Users
            SET education='{profile_form.education.data}', employment='{profile_form.employment.data}',
                music='{profile_form.music.data}', movie='{profile_form.movie.data}',
                nationality='{profile_form.nationality.data}', birthday='{profile_form.birthday.data}'
            WHERE username='{username}';
            """
        sqlite.query(update_profile)
        return redirect(url_for("profile", viewer=viewer, username=username))

    return render_template("profile.html.j2", title="Profile", username=viewer, user=owner, form=profile_form)


@app.route("/uploads/<string:filename>")
def uploads(filename):
    """Provides an endpoint for serving uploaded files."""
    return send_from_directory(Path(app.instance_path) / app.config["UPLOADS_FOLDER_PATH"], filename)
