using System.Linq;
using Avalonia;
using Avalonia.Controls;
using Avalonia.VisualTree;
using RbwrOverlay.UI.Behaviors;

namespace RbwrOverlay.UI.Views;

public partial class CompactOverlayView : UserControl
{
    public CompactOverlayView()
    {
        InitializeComponent();
    }

    protected override void OnAttachedToVisualTree(VisualTreeAttachmentEventArgs e)
    {
        base.OnAttachedToVisualTree(e);
        foreach (var tb in this.GetVisualDescendants().OfType<TextBox>())
        {
            TextBoxBehaviors.Attach(tb);
        }
    }
}