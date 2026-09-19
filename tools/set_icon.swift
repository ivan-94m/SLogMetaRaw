// SPDX-License-Identifier: GPL-3.0-or-later
// Sets a custom Finder icon on a file or folder: swift tools/set_icon.swift <icon.icns|png> <path>
import AppKit

let args = CommandLine.arguments
guard args.count == 3, let image = NSImage(contentsOfFile: args[1]) else {
    print("usage: set_icon.swift <icon> <path>")
    exit(1)
}
exit(NSWorkspace.shared.setIcon(image, forFile: args[2], options: []) ? 0 : 2)
