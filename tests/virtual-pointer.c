/* Test-only client for real Wayland pointer motion/click events.
 * Generate filmstrip-virtual-pointer.{h,c} in /tmp from wlr-protocols first.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <wayland-client.h>
#include "filmstrip-virtual-pointer.h"
static struct zwlr_virtual_pointer_manager_v1 *manager;
static void global(void *data, struct wl_registry *registry, uint32_t name,
                   const char *interface, uint32_t version) {
  if (!strcmp(interface, zwlr_virtual_pointer_manager_v1_interface.name))
    manager = wl_registry_bind(registry, name, &zwlr_virtual_pointer_manager_v1_interface, 1);
}
static void remove_global(void *data, struct wl_registry *registry, uint32_t name) {}
static const struct wl_registry_listener listener = {global, remove_global};
int main(int argc, char **argv) {
  if (argc < 5) return 2;
  struct wl_display *display = wl_display_connect(NULL);
  if (!display) return 3;
  struct wl_registry *registry = wl_display_get_registry(display);
  wl_registry_add_listener(registry, &listener, NULL);
  wl_display_roundtrip(display);
  if (!manager) { fprintf(stderr, "Virtual pointer unavailable\n"); return 4; }
  struct zwlr_virtual_pointer_v1 *pointer = zwlr_virtual_pointer_manager_v1_create_virtual_pointer(manager, NULL);
  struct timespec now; clock_gettime(CLOCK_MONOTONIC, &now);
  uint32_t time = now.tv_sec * 1000 + now.tv_nsec / 1000000;
  zwlr_virtual_pointer_v1_motion_absolute(pointer, time, atoi(argv[1]), atoi(argv[2]), atoi(argv[3]), atoi(argv[4]));
  zwlr_virtual_pointer_v1_frame(pointer);
  wl_display_roundtrip(display);
  if (argc == 6 && !strcmp(argv[5], "click")) {
    zwlr_virtual_pointer_v1_button(pointer, time + 1, 0x110, WL_POINTER_BUTTON_STATE_PRESSED);
    zwlr_virtual_pointer_v1_frame(pointer);
    zwlr_virtual_pointer_v1_button(pointer, time + 2, 0x110, WL_POINTER_BUTTON_STATE_RELEASED);
    zwlr_virtual_pointer_v1_frame(pointer);
    wl_display_roundtrip(display);
  }
  zwlr_virtual_pointer_v1_destroy(pointer);
  zwlr_virtual_pointer_manager_v1_destroy(manager);
  wl_registry_destroy(registry);
  wl_display_flush(display);
  wl_display_disconnect(display);
}
