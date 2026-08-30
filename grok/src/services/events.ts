export const DATA_CHANGED_EVENT = "mca-data-changed";

export function notifyDataChanged(): void {
  window.dispatchEvent(new Event(DATA_CHANGED_EVENT));
}
