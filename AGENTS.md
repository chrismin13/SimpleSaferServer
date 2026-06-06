Follow `docs/development.md` as the canonical coding standard for this repository.

Always sprinkle comments about things we might forget in a few months, or that might not immediately seem obvious on a first read.

Double check about documentation that might be related to whatever you are implementing, along with the related links to the index.html file. You are encouraged to rewrite and refactor the documentation whenever it is outdated or does not make sense to match the behavior seen in code.

When writing comments and documentation, don't write it assuming the person reading it has seen the previous version of the code or comments. For example don't do something like

# previously this did x
# now it does y

instead just do

# this does x


Prefer refactoring code if the end result will mean that the code will be simpler, more effective, and easier to maintain, rather than sticking to existing conventions, even if it means more work in the short term

When designing any UI elements, always use the uncodixfy skill. Try to reuse existing UI elements and UI patterns from elsewhere in the system or, if as a last resort creating new ones, follow the same "Bunker" style. Make good use of vertical space, so more things can be visible at once with your design. Consider how the page will be viewed both on desktop and mobile.

Consider if anything that you add needs to be removed during the uninstallation by the uninstall.sh script.

SimpleSaferServer is a root-run, admin-only local management tool. Admin users are trusted operators with server-level access, so do not hide useful managed secrets or config from them just for appearance; still avoid accidental leaks into logs, broad status responses, process argv, or unrelated UI.

Do not edit the README.md, any edits to it will be done by the user.
