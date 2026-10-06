using System.Linq;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.VisualTree;
using RbwrOverlay.UI.Behaviors;

namespace RbwrOverlay.UI.Views;

public partial class ServerSyncWindow : Window
{
    public ServerSyncWindow()
    {
        InitializeComponent();
        AddHandler(PointerPressedEvent, (s, e) =>
        {
            if (e.GetCurrentPoint(this).Properties.IsLeftButtonPressed &&
                e.Source is not TextBox && e.Source is not Button && e.Source is not AutoCompleteBox)
            {
                BeginMoveDrag(e);
            }
        });
    }

    protected override void OnAttachedToVisualTree(VisualTreeAttachmentEventArgs e)
    {
        base.OnAttachedToVisualTree(e);
        foreach (var acb in this.GetVisualDescendants().OfType<AutoCompleteBox>())
        {
            AutoCompleteBehaviors.ApplyJobIdFilter(acb);
        }
    }
}