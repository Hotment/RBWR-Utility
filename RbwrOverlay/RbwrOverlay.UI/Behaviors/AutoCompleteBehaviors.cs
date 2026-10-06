using System;
using System.Reflection;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Controls.Utils;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Threading;
using Avalonia.VisualTree;
using RbwrOverlay.Core.Services;
using RbwrOverlay.UI.ViewModels;

namespace RbwrOverlay.UI.Behaviors;

public static class AutoCompleteBehaviors
{
    private static readonly PropertyInfo? SelectionAdapterProp =
        typeof(AutoCompleteBox).GetProperty("SelectionAdapter", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);

    public static readonly AttachedProperty<bool> JobIdFilterProperty =
        AvaloniaProperty.RegisterAttached<AutoCompleteBox, bool>(
            "JobIdFilter",
            typeof(AutoCompleteBehaviors),
            defaultValue: false);

    private static readonly AttachedProperty<bool> IsConfiguredProperty =
        AvaloniaProperty.RegisterAttached<AutoCompleteBox, bool>(
            "IsConfigured",
            typeof(AutoCompleteBehaviors),
            defaultValue: false);

    public static bool GetJobIdFilter(AutoCompleteBox element) => element.GetValue(JobIdFilterProperty);
    public static void SetJobIdFilter(AutoCompleteBox element, bool value) => element.SetValue(JobIdFilterProperty, value);

    static AutoCompleteBehaviors()
    {
        JobIdFilterProperty.Changed.AddClassHandler<AutoCompleteBox>((box, e) =>
        {
            if (e.NewValue is true)
            {
                ApplyJobIdFilter(box);
            }
        });
    }

    public static void ApplyJobIdFilter(AutoCompleteBox box)
    {
        box.FilterMode = AutoCompleteFilterMode.Custom;
        box.ItemFilter = (search, item) => JobIdMatcher.IsMatch(search, item?.ToString());
        box.TextFilter = (search, item) => JobIdMatcher.IsMatch(search, item);

        if (box.GetValue(IsConfiguredProperty))
        {
            return;
        }
        box.SetValue(IsConfiguredProperty, true);

        string? currentCommittedText = null;
        string? lastSelectedId = null;
        string? lastSyncedId = null;
        DateTime lastSyncTime = DateTime.MinValue;
        bool isCommitting = false;
        ISelectionAdapter? currentAdapter = null;

        void CommitAndSync(AutoCompleteBox b, string targetId)
        {
            if (string.IsNullOrWhiteSpace(targetId)) return;
            targetId = targetId.Trim();

            currentCommittedText = targetId;
            lastSelectedId = null;

            isCommitting = true;
            b.Text = targetId;
            if (b.Text != null)
            {
                b.CaretIndex = b.Text.Length;
            }
            b.IsDropDownOpen = false;
            SyncViewModel(b, targetId);

            if (lastSyncedId != targetId || (DateTime.UtcNow - lastSyncTime).TotalMilliseconds > 500)
            {
                lastSyncedId = targetId;
                lastSyncTime = DateTime.UtcNow;
                TriggerSync(b, targetId);
            }

            isCommitting = false;

            Dispatcher.UIThread.Post(() =>
            {
                if (currentCommittedText == targetId)
                {
                    isCommitting = true;
                    b.Text = targetId;
                    if (b.Text != null)
                    {
                        b.CaretIndex = b.Text.Length;
                    }
                    SyncViewModel(b, targetId);
                    isCommitting = false;
                }
            }, DispatcherPriority.Input);
        }

        void AttachToAdapter(ISelectionAdapter? adapter)
        {
            if (adapter == null || adapter == currentAdapter) return;
            currentAdapter = adapter;

            adapter.Commit += (s, e) =>
            {
                string? picked = adapter.SelectedItem?.ToString() ?? lastSelectedId;
                if (!string.IsNullOrWhiteSpace(picked))
                {
                    CommitAndSync(box, picked);
                }
            };

            adapter.SelectionChanged += (s, e) =>
            {
                if (isCommitting) return;
                string? sel = null;
                if (e.AddedItems != null && e.AddedItems.Count > 0 && e.AddedItems[0] != null)
                {
                    sel = e.AddedItems[0]?.ToString();
                }
                else if (adapter.SelectedItem != null)
                {
                    sel = adapter.SelectedItem.ToString();
                }

                if (!string.IsNullOrWhiteSpace(sel))
                {
                    lastSelectedId = sel;
                }
            };

            if (adapter is SelectingItemsControlSelectionAdapter sa && sa.SelectorControl != null)
            {
                sa.SelectorControl.AddHandler(InputElement.PointerReleasedEvent, (sender, args) =>
                {
                    string? picked = sa.SelectedItem?.ToString() ?? sa.SelectorControl.SelectedItem?.ToString() ?? lastSelectedId;
                    if (!string.IsNullOrWhiteSpace(picked))
                    {
                        CommitAndSync(box, picked);
                    }
                }, RoutingStrategies.Bubble | RoutingStrategies.Tunnel, handledEventsToo: true);
            }
        }

        void TryAttachAdapter()
        {
            var adapter = SelectionAdapterProp?.GetValue(box) as ISelectionAdapter;
            if (adapter != null)
            {
                AttachToAdapter(adapter);
            }
        }

        box.TemplateApplied += (s, e) =>
        {
            TryAttachAdapter();
        };

        box.DropDownOpening += (s, e) =>
        {
            if (isCommitting)
            {
                e.Cancel = true;
                return;
            }
            TryAttachAdapter();
        };

        box.DropDownOpened += (s, e) =>
        {
            TryAttachAdapter();
        };

        box.SelectionChanged += (s, e) =>
        {
            if (isCommitting) return;

            string? selected = null;
            if (e.AddedItems != null && e.AddedItems.Count > 0 && e.AddedItems[0] != null)
            {
                selected = e.AddedItems[0]?.ToString();
            }
            else if (box.SelectedItem != null)
            {
                selected = box.SelectedItem.ToString();
            }

            if (!string.IsNullOrWhiteSpace(selected))
            {
                lastSelectedId = selected;
                CommitAndSync(box, selected);
            }
        };

        box.DropDownClosed += (s, e) =>
        {
            string? picked = currentAdapter?.SelectedItem?.ToString() ?? lastSelectedId;
            if (!string.IsNullOrWhiteSpace(picked))
            {
                lastSelectedId = null;
                CommitAndSync(box, picked);
            }
            else if (!string.IsNullOrWhiteSpace(currentCommittedText))
            {
                var target = currentCommittedText;
                Dispatcher.UIThread.Post(() =>
                {
                    isCommitting = true;
                    box.Text = target;
                    if (box.Text != null)
                    {
                        box.CaretIndex = box.Text.Length;
                    }
                    SyncViewModel(box, target);
                    isCommitting = false;
                }, DispatcherPriority.Input);
            }
        };

        box.PropertyChanged += (s, e) =>
        {
            if (e.Property == AutoCompleteBox.TextProperty)
            {
                if (currentCommittedText != null && !isCommitting)
                {
                    if (box.Text != currentCommittedText)
                    {
                        var target = currentCommittedText;
                        Dispatcher.UIThread.Post(() =>
                        {
                            if (currentCommittedText == target)
                            {
                                isCommitting = true;
                                box.Text = target;
                                if (box.Text != null)
                                {
                                    box.CaretIndex = box.Text.Length;
                                }
                                SyncViewModel(box, target);
                                isCommitting = false;
                            }
                        }, DispatcherPriority.Input);
                    }
                }
            }
        };

        box.Populating += (s, e) =>
        {
            if (isCommitting)
            {
                e.Cancel = true;
            }
        };

        box.AddHandler(InputElement.TextInputEvent, (sender, e) =>
        {
            currentCommittedText = null;
        }, RoutingStrategies.Tunnel);

        box.AddHandler(InputElement.KeyDownEvent, (sender, e) =>
        {
            if (e.Key == Key.Enter)
            {
                e.Handled = true;

                string targetId = string.Empty;
                if (box.SelectedItem is string sel && !string.IsNullOrWhiteSpace(sel))
                {
                    targetId = sel.Trim();
                }
                else if (!string.IsNullOrWhiteSpace(lastSelectedId))
                {
                    targetId = lastSelectedId.Trim();
                }
                else if (!string.IsNullOrWhiteSpace(currentCommittedText))
                {
                    targetId = currentCommittedText.Trim();
                }
                else if (!string.IsNullOrWhiteSpace(box.Text))
                {
                    targetId = box.Text.Trim();
                }

                if (!string.IsNullOrWhiteSpace(targetId))
                {
                    lastSyncedId = null;
                    CommitAndSync(box, targetId);
                }
            }
            else if (e.Key == Key.Escape)
            {
                lastSelectedId = null;
                currentCommittedText = null;
            }
            else if (e.Key != Key.Down && e.Key != Key.Up && e.Key != Key.Tab &&
                     e.Key != Key.Left && e.Key != Key.Right && e.Key != Key.Home && e.Key != Key.End &&
                     e.Key != Key.PageUp && e.Key != Key.PageDown &&
                     e.Key != Key.LeftShift && e.Key != Key.RightShift &&
                     e.Key != Key.LeftCtrl && e.Key != Key.RightCtrl &&
                     e.Key != Key.LeftAlt && e.Key != Key.RightAlt)
            {
                currentCommittedText = null;
            }
        }, RoutingStrategies.Tunnel, handledEventsToo: true);

        TryAttachAdapter();
    }

    private static void SyncViewModel(AutoCompleteBox box, string targetId)
    {
        if (string.IsNullOrWhiteSpace(targetId)) return;
        targetId = targetId.Trim();

        if (box.DataContext is MainOverlayViewModel mainVm)
        {
            mainVm.JobIdInput = targetId;
        }
        else if (box.DataContext is ServerSyncViewModel syncVm)
        {
            syncVm.JobIdInput = targetId;
        }
    }

    private static void TriggerSync(AutoCompleteBox box, string targetId)
    {
        if (string.IsNullOrWhiteSpace(targetId)) return;
        targetId = targetId.Trim();

        if (box.DataContext is MainOverlayViewModel mainVm)
        {
            mainVm.JobIdInput = targetId;
            if (mainVm.ConnectServerFromInputCommand.CanExecute(null))
            {
                mainVm.ConnectServerFromInputCommand.Execute(null);
            }
            else
            {
                _ = mainVm.ConnectServerAsync(targetId, true);
            }
        }
        else if (box.DataContext is ServerSyncViewModel syncVm)
        {
            syncVm.JobIdInput = targetId;
            if (syncVm.SyncCommand.CanExecute(null))
            {
                syncVm.SyncCommand.Execute(null);
            }
            else
            {
                syncVm.Sync();
            }
        }
    }
}