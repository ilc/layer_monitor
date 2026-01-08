{ pkgs ? import <nixpkgs> {} }:

let
  # hidapi with hidraw backend for proper usage_page support on Linux
  hidapiWithHidraw = pkgs.python3Packages.hidapi.overrideAttrs (old: {
    buildInputs = (old.buildInputs or []) ++ [ pkgs.systemdLibs ];
    NIX_CFLAGS_COMPILE = "-I${pkgs.systemdLibs.dev}/include";
  });
in
pkgs.mkShell {
  buildInputs = with pkgs; [
    python3
    python3Packages.pyside6
    hidapiWithHidraw
    python3Packages.pillow
    systemdLibs
  ];

  shellHook = ''
    export PYTHONPATH="${toString ./src/main/python}:$PYTHONPATH"
    echo "Layer Monitor dev shell"
    echo "Run: python3 src/main/python/main.py"
  '';
}
