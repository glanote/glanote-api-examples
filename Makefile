.PHONY: test syntax live

test: syntax
	python3 -m unittest tests.test_glanote_py
	node --test tests/test_glanote_js.mjs
	bash tests/test_glanote_sh.sh

syntax:
	python3 -m py_compile python/glanote.py tests/live_opt_in.py tests/test_glanote_py.py
	node --check javascript/glanote.mjs
	node --check tests/test_glanote_js.mjs
	bash -n shell/glanote.sh
	bash -n tests/test_glanote_sh.sh

live:
	@test "$$GLANOTE_LIVE" = "1" || { echo "Set GLANOTE_LIVE=1 to publish and delete at most 3 test articles"; exit 2; }
	python3 tests/live_opt_in.py --confirm-live
